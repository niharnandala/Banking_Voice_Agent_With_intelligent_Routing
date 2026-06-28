import json
import chromadb
from sentence_transformers import SentenceTransformer


# ============================================================
# WHAT THIS FILE DOES
# ============================================================
# reads bank_policies.jsonl
# converts each chunk into a vector embedding
# stores chunks + vectors + metadata in ChromaDB
#
# at query time:
# converts user question into a vector
# searches ChromaDB for similar vectors
# uses dynamic drop detection instead of fixed threshold
# returns only the most relevant chunks
#
# why dynamic drop detection instead of fixed threshold?
# fixed threshold like 0.7 is not reliable across all models and datasets
# for one model 0.65 might be excellent
# for another 0.82 might be average
# dynamic detection looks at the SHAPE of scores instead
# if scores are 0.91, 0.89, 0.85, 0.61, 0.58
# the big drop between 0.85 and 0.61 tells us 0.61 and below are not relevant
# we cut there and keep only the first 3


# ============================================================
# STEP 1 — LOAD THE EMBEDDING MODEL
# ============================================================
# SentenceTransformer converts text into vectors
# a vector is a list of 384 numbers representing the MEANING of text
# similar meaning = similar numbers = close in vector space
#
# all-MiniLM-L6-v2 is small, fast, accurate enough for FAQ search
# downloads automatically first time, cached after that

print("loading embedding model...")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("model loaded!")


# ============================================================
# STEP 2 — CONNECT TO CHROMADB
# ============================================================
# PersistentClient saves data to disk at ./chroma_db folder
# so next time we run, data is already there
# no need to re-embed everything from scratch

print("connecting to ChromaDB...")
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# collection is like a table in a normal database
# get_or_create means use existing or create fresh
# hnsw:space cosine means use cosine similarity for searching
bank_collection = chroma_client.get_or_create_collection(
    name     = "bank_policies",
    metadata = {"hnsw:space": "cosine"}
)
print("ChromaDB connected!")


# ============================================================
# STEP 3 — READ JSONL FILE
# ============================================================
# jsonl has one record per line
# each line is a valid json object
# we read line by line so we dont load everything into memory at once
# this is the production level approach for large datasets

def read_jsonl(filepath):

    print(f"\nreading {filepath}...")
    records = []

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                record = json.loads(line)
                records.append(record)

    print(f"read {len(records)} records from {filepath}")
    return records


# ============================================================
# STEP 4 — BUILD THE KNOWLEDGE BASE
# ============================================================
# reads all records from jsonl
# embeds the text field of each record into a vector
# stores text + vector + metadata in ChromaDB
#
# metadata = section, topic, section_index
# storing metadata means at search time we know
# which section each chunk came from
# useful for knowing where the answer came from

def build_knowledge_base(jsonl_file="bank_policies.jsonl"):

    # read all records from jsonl
    records = read_jsonl(jsonl_file)

    # prepare lists to store everything before sending to ChromaDB
    ids        = []
    texts      = []
    embeddings = []
    metadatas  = []

    print("\npreparing embeddings...")

    for record in records:

        # extract fields from each jsonl record
        chunk_id      = record["id"]
        text          = record["text"]
        section       = record["section"]
        topic         = record["topic"]
        section_index = record["section_index"]

        # convert text to vector embedding
        # model.encode returns a numpy array
        # .tolist() converts it to plain python list
        # ChromaDB needs plain python lists not numpy arrays
        embedding = model.encode(text).tolist()

        # collect everything into lists
        ids.append(chunk_id)
        texts.append(text)
        embeddings.append(embedding)

        # metadata is extra info stored alongside the vector
        # we can use this to filter searches later
        # eg only search within "EMI and Loan Repayment" section
        metadatas.append({
            "section"       : section,
            "topic"         : topic,
            "section_index" : section_index
        })

        print(f"  embedded: {chunk_id} — {section}")

    # store everything in ChromaDB in one batch call
    print("\nstoring in ChromaDB...")
    bank_collection.add(
        ids        = ids,
        documents  = texts,
        embeddings = embeddings,
        metadatas  = metadatas
    )

    print(f"\ndone! {len(records)} chunks stored in ChromaDB!")


# ============================================================
# STEP 5 — SEARCH THE KNOWLEDGE BASE
# ============================================================
# called at query time when user asks a question
#
# query          = user question or LLM framed version of it
# top_k          = how many candidates to fetch from ChromaDB initially
# max_results    = maximum chunks to return after filtering
# drop_threshold = if similarity drops by this much between two consecutive
#                  results we cut there and discard everything after
#
# example of dynamic drop detection:
# scores:  0.91  0.89  0.85  0.61  0.58
# gaps:         0.02  0.04  0.24  0.03
# gap of 0.24 between position 2 and 3 is bigger than drop_threshold 0.15
# so we cut there and keep only first 3 results
#
# this is better than a fixed threshold because:
# fixed threshold 0.7 might cut good results for one model
# and let bad results through for another model
# drop detection adapts to whatever scores this model produces

def search_knowledge_base(query, top_k=10, max_results=5, drop_threshold=0.15):

    print(f"\nsearching for: '{query}'")

    # convert question to vector
    query_embedding = model.encode(query).tolist()

    # search ChromaDB for top_k most similar vectors
    # include documents, distances, and metadatas in results
    raw_results = bank_collection.query(
        query_embeddings = [query_embedding],
        n_results        = top_k,
        include          = ["documents", "distances", "metadatas"]
    )

    # raw_results structure:
    # {
    #   "documents" : [["chunk text 1", "chunk text 2", ...]],
    #   "distances" : [[0.12, 0.34, 0.45, ...]],
    #   "metadatas" : [[{"section": "EMI...", ...}, ...]]
    # }
    # note: results are already sorted by distance (closest first)
    # distance and similarity are opposites:
    # similarity = 1 - distance
    # distance 0.1 = similarity 0.9 = very relevant
    # distance 0.8 = similarity 0.2 = not relevant at all

    chunks    = raw_results["documents"][0]
    distances = raw_results["distances"][0]
    metadatas = raw_results["metadatas"][0]

    # convert distances to similarities and build result objects
    scored = []

    for chunk, distance, metadata in zip(chunks, distances, metadatas):

        similarity = round(1 - distance, 3)

        scored.append({
            "text"          : chunk,
            "similarity"    : similarity,
            "section"       : metadata["section"],
            "topic"         : metadata["topic"],
            "section_index" : metadata["section_index"]
        })

    # sort by similarity highest first just to be safe
    scored.sort(key=lambda x: x["similarity"], reverse=True)

    # dynamic drop detection
    # always keep the best result
    # then check the gap between each consecutive pair
    # if gap is bigger than drop_threshold, cut there
    filtered = [scored[0]]

    for i in range(1, len(scored)):

        gap = scored[i - 1]["similarity"] - scored[i]["similarity"]

        if gap > drop_threshold:
            print(f"  drop detected at position {i}")
            print(f"  gap: {gap} is bigger than threshold: {drop_threshold}")
            print(f"  cutting here — discarding remaining {len(scored) - i} results")
            break

        filtered.append(scored[i])

    # cap at max_results just in case no big drop was found
    filtered = filtered[:max_results]

    # print what we kept
    print(f"\nkept {len(filtered)} chunks after drop detection:")
    for r in filtered:
        print(f"  similarity: {r['similarity']} — section: {r['section']}")

    if not filtered:
        print("  no results found — will escalate to human agent")

    return filtered


# ============================================================
# RUN — BUILD AND TEST
# ============================================================
# run this file once to build the knowledge base
# after this ChromaDB has everything saved on disk
# you never need to run build_knowledge_base() again
# unless bank_policies.jsonl changes

if __name__ == "__main__":

    # build the knowledge base from jsonl
    build_knowledge_base()

    # test search with sample questions
    print("\n" + "=" * 60)
    print("testing search")
    print("=" * 60)

    test_queries = [
        "what is the late payment charge for missing EMI",
        "how do i activate mobile banking",
        "what is the interest rate on fixed deposit"
    ]

    for query in test_queries:
        results = search_knowledge_base(query)
        print(f"\nresults for: '{query}'")
        print("-" * 60)
        for i, result in enumerate(results):
            print(f"\n  result {i + 1}")
            print(f"  similarity : {result['similarity']}")
            print(f"  section    : {result['section']}")
            print(f"  text       : {result['text'][:200]}...")
        print()
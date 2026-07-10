import json
import re


# ============================================================
# WHAT THIS FILE DOES
# ============================================================
# reads bank_policies.txt
# detects each numbered section automatically using regex
# splits each section into smaller overlapping chunks
# saves everything asgit bank_policies.jsonl
#
# each line in the jsonl file looks like this:
# {
#   "id"            : "section_1_chunk_0",
#   "section_index" : 1,
#   "section"       : "Account Types and Minimum Balance",
#   "topic"         : "account types and minimum balance",
#   "text"          : "XYZ Bank offers three types of savings accounts..."
# }
#
# why jsonl and not plain json?
# json = one big object, entire file loaded into memory at once
# jsonl = one object per line, read line by line
# for large bank datasets with thousands of policies,
# jsonl is much faster and memory efficient


# ============================================================
# STEP 1 — READ THE POLICY FILE
# ============================================================

def read_policy_file(filepath):

    print(f"reading {filepath}...")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    print("file read!")
    return content


# ============================================================
# STEP 2 — DETECT AND SPLIT INTO SECTIONS AUTOMATICALLY
# ============================================================
# our bank_policies.txt has sections like:
# "1. Account Types and Minimum Balance"
# "2. EMI and Loan Repayment"
# "3. Interest Rates"
#
# regex pattern explanation:
# \n       = newline (section always starts on new line)
# \d+      = one or more digits (section number like 1, 2, 3)
# \.       = literal dot after the number
# \s+      = one or more spaces
# [A-Z]    = capital letter (section title starts with capital)
#
# after splitting we skip anything that does not start with a digit
# this removes the title line at the top of the file
# "XYZ Bank — Policies and General Information"
# which was being counted as a section and shifting all ids by one

def split_into_sections(full_text):

    print("detecting sections...")

    section_pattern = r'\n(?=\d+\.\s+[A-Z])'
    raw_sections    = re.split(section_pattern, full_text)

    sections = []

    for s in raw_sections:
        s = s.strip()

        if not s:
            continue

        # only keep sections that start with a number
        # skips the title line at the top of the file
        if re.match(r'^\d+\.', s):
            sections.append(s)

    print(f"found {len(sections)} sections")
    return sections


# ============================================================
# STEP 3 — EXTRACT SECTION NAME FROM EACH SECTION
# ============================================================
# each section starts with "1. Account Types and Minimum Balance"
# we extract just "Account Types and Minimum Balance"
# and store it as metadata

def extract_section_name(section_text):

    # first line of each section is the heading
    first_line = section_text.split('\n')[0].strip()

    # remove the number and dot from the start
    # "1. Account Types" becomes "Account Types"
    section_name = re.sub(r'^\d+\.\s+', '', first_line)

    return section_name


# ============================================================
# STEP 4 — CHUNK EACH SECTION INTO SMALLER PIECES
# ============================================================
# we do not embed the entire section as one big vector
# because that loses precision when searching
#
# instead we split each section into smaller overlapping chunks
#
# chunk_size = 100 words per chunk
#              smaller than before because we already have
#              section level organisation from jsonl metadata
#
# overlap    = 20 words shared between consecutive chunks
#              prevents answers being cut off at chunk boundaries
#              if the answer spans end of chunk 1 and start of chunk 2
#              overlap ensures the answer appears fully in at least one chunk

def chunk_section(section_text, chunk_size=100, overlap=20):

    # remove the heading line before chunking
    # heading is stored as metadata, not as part of chunk text
    lines     = section_text.split('\n')
    body_text = '\n'.join(lines[1:]).strip()

    words  = body_text.split()
    chunks = []
    start  = 0

    while start < len(words):

        end   = start + chunk_size
        chunk = " ".join(words[start:end])

        # only add non empty chunks
        if chunk.strip():
            chunks.append(chunk)

        # step forward but step back by overlap
        # creates the shared words between consecutive chunks
        start = end - overlap

    return chunks


# ============================================================
# STEP 5 — GENERATE TOPIC FROM SECTION NAME
# ============================================================
# topic is just the section name in lowercase
# every chunk in the same section shares the same topic
# this is clean and consistent
#
# why not generate topic from chunk text?
# chunk text can start mid sentence due to overlap
# which gives messy topics like "the branch or raise a"
# section name always gives clean topics like "emi and loan repayment"

def generate_topic(section_name):
    return section_name.lower()


# ============================================================
# STEP 6 — CONVERT AND SAVE AS JSONL
# ============================================================
# puts everything together
# reads the policy file
# detects sections
# chunks each section
# builds a record for each chunk with full metadata
# writes everything to bank_policies.jsonl

def convert_to_jsonl(input_file, output_file):

    # read the policy file
    full_text = read_policy_file(input_file)

    # split into sections
    sections = split_into_sections(full_text)

    print("converting sections to chunks and building jsonl records...")

    all_records  = []
    total_chunks = 0

    for section_index, section in enumerate(sections):

        # extract section name for metadata
        section_name = extract_section_name(section)

        # generate topic from section name
        topic = generate_topic(section_name)

        # split this section into chunks
        chunks = chunk_section(section)

        for chunk_index, chunk in enumerate(chunks):

            # unique id for each chunk
            # eg section_1_chunk_0, section_1_chunk_1, section_2_chunk_0
            chunk_id = f"section_{section_index + 1}_chunk_{chunk_index}"

            # build the full record with all metadata
            record = {
                "id"            : chunk_id,
                "section_index" : section_index + 1,
                "section"       : section_name,
                "topic"         : topic,
                "text"          : chunk
            }

            all_records.append(record)
            total_chunks += 1

        print(f"  section {section_index + 1} — {section_name} — {len(chunks)} chunks")

    # write all records to jsonl file
    # each record on its own line as valid json
    print(f"\nwriting {total_chunks} chunks to {output_file}...")

    with open(output_file, "w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record) + "\n")

    print(f"done! {total_chunks} chunks written to {output_file}")
    return all_records


# ============================================================
# STEP 7 — PREVIEW THE OUTPUT
# ============================================================
# prints first few records so we can verify everything looks correct
# before moving to the embedding step

def preview_jsonl(output_file, num_records=3):

    print(f"\npreview of first {num_records} records from {output_file}:")
    print("=" * 60)

    with open(output_file, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= num_records:
                break
            record = json.loads(line)
            print(f"\nrecord {i + 1}:")
            print(f"  id            : {record['id']}")
            print(f"  section_index : {record['section_index']}")
            print(f"  section       : {record['section']}")
            print(f"  topic         : {record['topic']}")
            print(f"  text preview  : {record['text'][:150]}...")
            print("-" * 60)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    input_file  = "bank_policies.txt"
    output_file = "bank_policies.jsonl"

    records = convert_to_jsonl(input_file, output_file)
    preview_jsonl(output_file)
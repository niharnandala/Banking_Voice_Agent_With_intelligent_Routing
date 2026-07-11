<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XYZ Bank Voice Agent</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@300;400;500;600&display=swap');

  :root {
    --bg:        #0a0a0f;
    --surface:   #111118;
    --border:    #1e1e2e;
    --accent:    #f59e0b;
    --accent2:   #3b82f6;
    --green:     #10b981;
    --red:       #ef4444;
    --muted:     #4b5563;
    --text:      #e2e8f0;
    --textsoft:  #94a3b8;
    --mono:      'JetBrains Mono', monospace;
    --sans:      'Inter', sans-serif;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-size: 15px;
    line-height: 1.7;
  }

  /* ── HERO ── */
  .hero {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 80px 10vw;
    border-bottom: 1px solid var(--border);
    position: relative;
    overflow: hidden;
  }

  .hero::before {
    content: '';
    position: absolute;
    top: -200px; right: -200px;
    width: 600px; height: 600px;
    background: radial-gradient(circle, rgba(245,158,11,0.06) 0%, transparent 70%);
    pointer-events: none;
  }

  .hero-tag {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--accent);
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 24px;
  }

  .hero-title {
    font-size: clamp(36px, 6vw, 72px);
    font-weight: 600;
    line-height: 1.1;
    margin-bottom: 24px;
    letter-spacing: -1px;
  }

  .hero-title span { color: var(--accent); }

  .hero-sub {
    font-size: 18px;
    color: var(--textsoft);
    max-width: 560px;
    margin-bottom: 48px;
    font-weight: 300;
  }

  .hero-metrics {
    display: flex;
    gap: 48px;
    flex-wrap: wrap;
  }

  .metric {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .metric-num {
    font-family: var(--mono);
    font-size: 32px;
    font-weight: 700;
    color: var(--accent);
  }

  .metric-label {
    font-size: 12px;
    color: var(--muted);
    letter-spacing: 1px;
    text-transform: uppercase;
  }

  /* ── LIVE TERMINAL ── */
  .terminal-section {
    padding: 80px 10vw;
    border-bottom: 1px solid var(--border);
  }

  .section-eyebrow {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--accent);
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 16px;
  }

  .section-title {
    font-size: 28px;
    font-weight: 600;
    margin-bottom: 8px;
  }

  .section-sub {
    color: var(--textsoft);
    margin-bottom: 40px;
    font-size: 15px;
  }

  .terminal {
    background: #050508;
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    max-width: 860px;
  }

  .terminal-bar {
    background: #111118;
    padding: 12px 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid var(--border);
  }

  .dot { width: 10px; height: 10px; border-radius: 50%; }
  .dot-r { background: #ef4444; }
  .dot-y { background: #f59e0b; }
  .dot-g { background: #10b981; }

  .terminal-label {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--muted);
    margin-left: 8px;
  }

  .terminal-body {
    padding: 24px;
    font-family: var(--mono);
    font-size: 13px;
    line-height: 2;
  }

  .t-muted   { color: var(--muted); }
  .t-accent  { color: var(--accent); }
  .t-green   { color: var(--green); }
  .t-blue    { color: var(--accent2); }
  .t-red     { color: var(--red); }
  .t-white   { color: var(--text); }
  .t-user    { color: #c084fc; }

  /* ── HOW IT WORKS ── */
  .flow-section {
    padding: 80px 10vw;
    border-bottom: 1px solid var(--border);
  }

  .flow-diagram {
    display: flex;
    align-items: stretch;
    gap: 0;
    margin-top: 48px;
    flex-wrap: wrap;
  }

  .flow-step {
    flex: 1;
    min-width: 140px;
    display: flex;
    flex-direction: column;
    align-items: center;
    position: relative;
  }

  .flow-step:not(:last-child)::after {
    content: '→';
    position: absolute;
    right: -12px;
    top: 28px;
    color: var(--muted);
    font-size: 18px;
    z-index: 1;
  }

  .flow-box {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px 16px;
    text-align: center;
    width: 100%;
    transition: border-color 0.2s;
  }

  .flow-box:hover { border-color: var(--accent); }

  .flow-icon {
    font-size: 24px;
    margin-bottom: 8px;
  }

  .flow-name {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--accent);
    font-weight: 600;
    margin-bottom: 6px;
  }

  .flow-desc {
    font-size: 12px;
    color: var(--textsoft);
    line-height: 1.5;
  }

  /* ── ROUTING DIAGRAM ── */
  .routing-section {
    padding: 80px 10vw;
    border-bottom: 1px solid var(--border);
  }

  .routing-diagram {
    margin-top: 48px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    max-width: 800px;
  }

  .routing-center {
    background: var(--surface);
    border: 2px solid var(--accent);
    border-radius: 8px;
    padding: 16px 32px;
    font-family: var(--mono);
    font-size: 13px;
    color: var(--accent);
    font-weight: 700;
    text-align: center;
    margin-bottom: 0;
  }

  .routing-arrow-down {
    width: 2px;
    height: 24px;
    background: var(--muted);
    margin: 0 auto;
  }

  .routing-branches {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    justify-content: center;
    margin-top: 24px;
    width: 100%;
  }

  .routing-branch {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    flex: 1;
    min-width: 140px;
    max-width: 180px;
  }

  .branch-label {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    margin-bottom: 8px;
  }

  .branch-desc {
    font-size: 12px;
    color: var(--textsoft);
    line-height: 1.5;
  }

  .branch-personal  .branch-label { color: var(--accent2); }
  .branch-general   .branch-label { color: var(--green); }
  .branch-escalate  .branch-label { color: var(--red); }
  .branch-smalltalk .branch-label { color: #c084fc; }
  .branch-exit      .branch-label { color: var(--muted); }

  .branch-personal  { border-color: rgba(59,130,246,0.3); }
  .branch-general   { border-color: rgba(16,185,129,0.3); }
  .branch-escalate  { border-color: rgba(239,68,68,0.3); }
  .branch-smalltalk { border-color: rgba(192,132,252,0.3); }
  .branch-exit      { border-color: rgba(75,85,99,0.3); }

  /* ── DECISIONS ── */
  .decisions-section {
    padding: 80px 10vw;
    border-bottom: 1px solid var(--border);
  }

  .decision-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 20px;
    margin-top: 48px;
  }

  .decision-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 28px;
  }

  .decision-q {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--muted);
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 8px;
  }

  .decision-choice {
    font-size: 16px;
    font-weight: 600;
    color: var(--accent);
    margin-bottom: 12px;
  }

  .decision-reason {
    font-size: 13px;
    color: var(--textsoft);
    line-height: 1.7;
  }

  .vs-line {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 8px 0;
    font-family: var(--mono);
    font-size: 12px;
  }

  .vs-chosen { color: var(--green); }
  .vs-not    { color: var(--muted); text-decoration: line-through; }

  /* ── DROP DETECTION ── */
  .drop-visual {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 28px;
    margin-top: 24px;
    max-width: 600px;
  }

  .score-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
  }

  .score-label {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--textsoft);
    width: 80px;
  }

  .score-bar-wrap {
    flex: 1;
    background: var(--border);
    border-radius: 4px;
    height: 8px;
    overflow: hidden;
  }

  .score-bar {
    height: 100%;
    border-radius: 4px;
    transition: width 1s ease;
  }

  .score-val {
    font-family: var(--mono);
    font-size: 12px;
    width: 40px;
    text-align: right;
  }

  .score-keep .score-bar  { background: var(--green); }
  .score-keep .score-val  { color: var(--green); }
  .score-cut  .score-bar  { background: var(--muted); }
  .score-cut  .score-val  { color: var(--muted); }

  .drop-marker {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--accent);
    margin: 8px 0 8px 92px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .drop-line {
    height: 1px;
    flex: 1;
    background: var(--accent);
    opacity: 0.5;
  }

  /* ── FIXES ── */
  .fixes-section {
    padding: 80px 10vw;
    border-bottom: 1px solid var(--border);
  }

  .fix-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-top: 48px;
    max-width: 760px;
  }

  .fix-item {
    display: grid;
    grid-template-columns: 200px 1fr;
    gap: 24px;
    padding: 20px 24px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    align-items: start;
  }

  .fix-name {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--accent);
    font-weight: 600;
    padding-top: 2px;
  }

  .fix-what {
    font-size: 13px;
    color: var(--textsoft);
    line-height: 1.7;
  }

  /* ── INDUSTRIES ── */
  .industries-section {
    padding: 80px 10vw;
    border-bottom: 1px solid var(--border);
  }

  .industry-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 20px;
    margin-top: 48px;
  }

  .industry-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 28px;
    transition: border-color 0.2s;
  }

  .industry-card:hover { border-color: var(--accent2); }

  .industry-icon  { font-size: 28px; margin-bottom: 12px; }
  .industry-name  { font-size: 15px; font-weight: 600; margin-bottom: 8px; }
  .industry-value {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--accent);
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 10px;
  }
  .industry-desc  { font-size: 13px; color: var(--textsoft); line-height: 1.6; }

  /* ── FILES ── */
  .files-section {
    padding: 80px 10vw;
    border-bottom: 1px solid var(--border);
  }

  .file-tree {
    font-family: var(--mono);
    font-size: 13px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 28px;
    max-width: 680px;
    margin-top: 40px;
    line-height: 2.2;
  }

  .ft-dir   { color: var(--accent2); }
  .ft-file  { color: var(--text); }
  .ft-desc  { color: var(--muted); font-size: 11px; margin-left: 8px; }

  /* ── ROADMAP ── */
  .roadmap-section {
    padding: 80px 10vw;
    border-bottom: 1px solid var(--border);
  }

  .roadmap-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
    margin-top: 48px;
  }

  .roadmap-col-title {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }

  .col-done    .roadmap-col-title { color: var(--green); }
  .col-doing   .roadmap-col-title { color: var(--accent); }
  .col-planned .roadmap-col-title { color: var(--accent2); }

  .roadmap-item {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 13px;
    color: var(--textsoft);
    margin-bottom: 10px;
    line-height: 1.5;
  }

  .ri-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    margin-top: 6px;
    flex-shrink: 0;
  }

  .col-done    .ri-dot { background: var(--green); }
  .col-doing   .ri-dot { background: var(--accent); }
  .col-planned .ri-dot { background: var(--accent2); }

  /* ── SETUP ── */
  .setup-section {
    padding: 80px 10vw;
    border-bottom: 1px solid var(--border);
  }

  .setup-steps {
    display: flex;
    flex-direction: column;
    gap: 16px;
    max-width: 680px;
    margin-top: 40px;
  }

  .setup-step {
    display: grid;
    grid-template-columns: 40px 1fr;
    gap: 16px;
    align-items: start;
  }

  .step-num {
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 700;
    color: var(--accent);
    background: rgba(245,158,11,0.08);
    border: 1px solid rgba(245,158,11,0.2);
    border-radius: 6px;
    width: 36px; height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .step-body { padding-top: 6px; }

  .step-title {
    font-size: 14px;
    font-weight: 500;
    margin-bottom: 8px;
  }

  pre {
    background: #050508;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px 16px;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--green);
    overflow-x: auto;
    margin-top: 8px;
  }

  /* ── TRADEOFFS ── */
  .tradeoffs-section {
    padding: 80px 10vw;
    border-bottom: 1px solid var(--border);
  }

  .tradeoff-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: 40px;
    max-width: 680px;
  }

  .tradeoff-item {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid var(--border);
  }

  .to-left {
    background: rgba(239,68,68,0.06);
    padding: 16px;
    font-size: 13px;
    color: var(--textsoft);
  }

  .to-right {
    background: rgba(16,185,129,0.06);
    padding: 16px;
    font-size: 13px;
    color: var(--textsoft);
  }

  .to-label {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 4px;
  }

  .to-left  .to-label { color: var(--red); }
  .to-right .to-label { color: var(--green); }

  /* ── FOOTER ── */
  .footer {
    padding: 60px 10vw;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: gap;
    gap: 20px;
  }

  .footer-name {
    font-family: var(--mono);
    font-size: 14px;
    color: var(--textsoft);
  }

  .footer-link {
    font-family: var(--mono);
    font-size: 13px;
    color: var(--accent);
    text-decoration: none;
    border-bottom: 1px solid rgba(245,158,11,0.3);
    padding-bottom: 2px;
  }

  .footer-link:hover { color: var(--text); border-color: var(--text); }

  /* ── LANG BADGES ── */
  .lang-badges {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 16px;
  }

  .badge {
    font-family: var(--mono);
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 4px;
    border: 1px solid;
    letter-spacing: 1px;
  }

  .badge-en { color: var(--accent2);  border-color: rgba(59,130,246,0.3);  background: rgba(59,130,246,0.06); }
  .badge-hi { color: #f97316;         border-color: rgba(249,115,22,0.3);  background: rgba(249,115,22,0.06); }
  .badge-te { color: #a78bfa;         border-color: rgba(167,139,250,0.3); background: rgba(167,139,250,0.06); }
  .badge-hh { color: var(--green);    border-color: rgba(16,185,129,0.3);  background: rgba(16,185,129,0.06); }

  @media (max-width: 640px) {
    .roadmap-grid   { grid-template-columns: 1fr; }
    .fix-item       { grid-template-columns: 1fr; }
    .tradeoff-item  { grid-template-columns: 1fr; }
    .flow-step:not(:last-child)::after { display: none; }
  }
</style>
</head>
<body>

<!-- ── HERO ── -->
<section class="hero">
  <div class="hero-tag">Open Source · Voice AI · Indian Languages</div>
  <h1 class="hero-title">
    A voice agent that<br>
    actually <span>understands</span><br>
    how Indians speak
  </h1>
  <p class="hero-sub">
    Built for XYZ Bank. Deployable for any industry.
    Handles English, Hindi, Telugu, and every mix in between —
    in under 4 seconds per turn.
  </p>
  <div class="lang-badges">
    <span class="badge badge-en">English</span>
    <span class="badge badge-hi">Hindi हिंदी</span>
    <span class="badge badge-te">Telugu తెలుగు</span>
    <span class="badge badge-hh">Hinglish / Tenglish</span>
  </div>
  <div class="hero-metrics" style="margin-top:48px;">
    <div class="metric">
      <span class="metric-num">&lt; 4s</span>
      <span class="metric-label">per full turn</span>
    </div>
    <div class="metric">
      <span class="metric-num">5</span>
      <span class="metric-label">intent types</span>
    </div>
    <div class="metric">
      <span class="metric-num">4</span>
      <span class="metric-label">languages</span>
    </div>
    <div class="metric">
      <span class="metric-num">0</span>
      <span class="metric-label">costly LLMs</span>
    </div>
  </div>
</section>

<!-- ── LIVE SESSION ── -->
<section class="terminal-section">
  <div class="section-eyebrow">Real output · no edits</div>
  <h2 class="section-title">What a real call looks like</h2>
  <p class="section-sub">Pulled directly from a live session. Hindi response, English question, mixed mid-call.</p>

  <div class="terminal">
    <div class="terminal-bar">
      <div class="dot dot-r"></div>
      <div class="dot dot-y"></div>
      <div class="dot dot-g"></div>
      <span class="terminal-label">python llm_intent.py</span>
    </div>
    <div class="terminal-body">
      <div class="t-green">bot: &nbsp; Hello, welcome to XYZ Bank. Ask me anything about your account.</div>
      <br>
      <div class="t-user">user: &nbsp;mera balance kya hai</div>
      <div class="t-muted">intent: personal, confidence: 0.95</div>
      <div class="t-green">bot: &nbsp; Please tell me your customer id.</div>
      <br>
      <div class="t-user">user: &nbsp;my customer id is cu 007</div>
      <div class="t-muted">customer_id: CU007 &nbsp;·&nbsp; verified in DB &nbsp;·&nbsp; data fetched</div>
      <div class="t-green">bot: &nbsp; Dhanyawad sir. Aapka balance 1.5 lakh rupees hai.</div>
      <br>
      <div class="t-user">user: &nbsp;could you get me some bank emi policies</div>
      <div class="t-muted">intent: general, confidence: 0.80</div>
      <div class="t-muted">kept 5 chunks after drop detection</div>
      <div class="t-green">bot: &nbsp; EMI har mahine 5 ko automatically deducted hota hai sir.</div>
      <div class="t-green">&nbsp; &nbsp; &nbsp; &nbsp;Bounce charge 500 rupees per instance hai.</div>
      <br>
      <div class="t-user">user: &nbsp;i want to change my bank account</div>
      <div class="t-muted">intent: escalate, confidence: 0.85</div>
      <div class="t-accent">ESCALATION TICKET RAISED · ticket id: 43A5E499</div>
      <div class="t-green">bot: &nbsp; I have raised a ticket for you sir. Staff will contact you shortly.</div>
    </div>
  </div>
</section>

<!-- ── HOW IT WORKS ── -->
<section class="flow-section">
  <div class="section-eyebrow">Architecture</div>
  <h2 class="section-title">Five steps. Every single call.</h2>
  <p class="section-sub">Same pipeline regardless of language, intent, or complexity.</p>

  <div class="flow-diagram">
    <div class="flow-step">
      <div class="flow-box">
        <div class="flow-icon">🎙️</div>
        <div class="flow-name">LISTEN</div>
        <div class="flow-desc">Vachana STT streams audio in real time. 1.5s silence = turn complete.</div>
      </div>
    </div>
    <div class="flow-step">
      <div class="flow-box">
        <div class="flow-icon">🧠</div>
        <div class="flow-name">UNDERSTAND</div>
        <div class="flow-desc">LLM classifies intent from full conversation history. Works in 4 languages.</div>
      </div>
    </div>
    <div class="flow-step">
      <div class="flow-box">
        <div class="flow-icon">⚡</div>
        <div class="flow-name">ROUTE</div>
        <div class="flow-desc">5 intent paths. Each one handled by a dedicated function.</div>
      </div>
    </div>
    <div class="flow-step">
      <div class="flow-box">
        <div class="flow-icon">🗄️</div>
        <div class="flow-name">FETCH</div>
        <div class="flow-desc">Real data only. DB for personal queries. ChromaDB for policy questions.</div>
      </div>
    </div>
    <div class="flow-step">
      <div class="flow-box">
        <div class="flow-icon">🔊</div>
        <div class="flow-name">RESPOND</div>
        <div class="flow-desc">Natural spoken reply. Mic reopens only after bot finishes talking.</div>
      </div>
    </div>
  </div>
</section>

<!-- ── ROUTING ── -->
<section class="routing-section">
  <div class="section-eyebrow">Intent Routing</div>
  <h2 class="section-title">One classifier. Five paths. Nothing falls through.</h2>
  <p class="section-sub">Every possible thing a caller can say maps to exactly one of these.</p>

  <div style="margin-top:48px; max-width:700px;">
    <div style="text-align:center;">
      <div class="routing-center">LLM Intent Classifier</div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:8px;">
        confidence ≥ 0.7 to route · below 0.7 asks user to repeat
      </div>
    </div>
    <div class="routing-branches">
      <div class="routing-branch branch-personal">
        <div class="branch-label">PERSONAL</div>
        <div class="branch-desc">Verify customer ID → DB lookup → answer from real account data</div>
      </div>
      <div class="routing-branch branch-general">
        <div class="branch-label">GENERAL</div>
        <div class="branch-desc">Vector search → dynamic drop detection → answer from policy chunks</div>
      </div>
      <div class="routing-branch branch-escalate">
        <div class="branch-label">ESCALATE</div>
        <div class="branch-desc">Generate ticket with full context → hand off to staff → end call</div>
      </div>
      <div class="routing-branch branch-smalltalk">
        <div class="branch-label">SMALLTALK</div>
        <div class="branch-desc">Clear history → reintroduce bot → listen for real question</div>
      </div>
      <div class="routing-branch branch-exit">
        <div class="branch-label">EXIT</div>
        <div class="branch-desc">Speak goodbye → break main loop → program ends cleanly</div>
      </div>
    </div>
  </div>
</section>

<!-- ── DECISIONS ── -->
<section class="decisions-section">
  <div class="section-eyebrow">Why these tools</div>
  <h2 class="section-title">Every choice has a reason.</h2>
  <p class="section-sub">Not defaults. Not what the tutorial used.</p>

  <div class="decision-grid">
    <div class="decision-card">
      <div class="decision-q">Speech to Text</div>
      <div class="decision-choice">Vachana by Gnani.ai</div>
      <div class="vs-line"><span class="vs-chosen">✓ Vachana</span></div>
      <div class="vs-line"><span class="vs-not">✗ Whisper</span></div>
      <div class="vs-line"><span class="vs-not">✗ Azure Speech</span></div>
      <div class="decision-reason">
        Trained on 1M+ hours of real Indian voice data across BFSI.
        Generic models fail on "see you zero zero one" and mid-sentence code-switching.
        Vachana does not.
      </div>
    </div>

    <div class="decision-card">
      <div class="decision-q">LLM Inference</div>
      <div class="decision-choice">Groq + LLaMA 3.1 8B Instant</div>
      <div class="vs-line"><span class="vs-chosen">✓ Groq</span></div>
      <div class="vs-line"><span class="vs-not">✗ OpenAI GPT-4</span></div>
      <div class="vs-line"><span class="vs-not">✗ Gemini</span></div>
      <div class="decision-reason">
        Sub-100ms inference for classification tasks.
        OpenAI at the same model size is 3 to 5x slower.
        On a voice call every second of silence feels wrong to a caller.
      </div>
    </div>

    <div class="decision-card">
      <div class="decision-q">Vector Search</div>
      <div class="decision-choice">ChromaDB + all-MiniLM-L6-v2</div>
      <div class="vs-line"><span class="vs-chosen">✓ ChromaDB local</span></div>
      <div class="vs-line"><span class="vs-not">✗ Pinecone</span></div>
      <div class="vs-line"><span class="vs-not">✗ Weaviate</span></div>
      <div class="decision-reason">
        Runs locally with zero API cost.
        384-dimension embeddings load once at startup and stay in memory.
        Fast enough for real-time retrieval on commodity hardware.
      </div>
    </div>

    <div class="decision-card">
      <div class="decision-q">ID Extraction</div>
      <div class="decision-choice">LLM over Regex</div>
      <div class="vs-line"><span class="vs-chosen">✓ LLM extraction</span></div>
      <div class="vs-line"><span class="vs-not">✗ Regex patterns</span></div>
      <div class="decision-reason">
        "see you zero zero one", "c u 001", "cu forty five" — callers say IDs
        in ways no regex handles well.
        The LLM reads the intent, not the characters.
      </div>
    </div>
  </div>

  <!-- Drop Detection Visual -->
  <div style="margin-top:40px;">
    <div style="font-size:14px;font-weight:500;margin-bottom:8px;">Dynamic Drop Detection — why fixed thresholds fail</div>
    <div style="font-size:13px;color:var(--textsoft);margin-bottom:20px;max-width:560px;">
      A fixed threshold of 0.7 is unreliable. For one model 0.65 is excellent,
      for another 0.82 is average. This system looks at the gap between scores instead.
    </div>
    <div class="drop-visual">
      <div class="score-row score-keep">
        <div class="score-label">chunk 1</div>
        <div class="score-bar-wrap"><div class="score-bar" style="width:91%"></div></div>
        <div class="score-val">0.91</div>
      </div>
      <div class="score-row score-keep">
        <div class="score-label">chunk 2</div>
        <div class="score-bar-wrap"><div class="score-bar" style="width:89%"></div></div>
        <div class="score-val">0.89</div>
      </div>
      <div class="score-row score-keep">
        <div class="score-label">chunk 3</div>
        <div class="score-bar-wrap"><div class="score-bar" style="width:85%"></div></div>
        <div class="score-val">0.85</div>
      </div>
      <div class="drop-marker">
        <div class="drop-line"></div>
        ↑ gap of 0.24 detected · cut here
        <div class="drop-line"></div>
      </div>
      <div class="score-row score-cut">
        <div class="score-label">chunk 4</div>
        <div class="score-bar-wrap"><div class="score-bar" style="width:61%"></div></div>
        <div class="score-val">0.61</div>
      </div>
      <div class="score-row score-cut">
        <div class="score-label">chunk 5</div>
        <div class="score-bar-wrap"><div class="score-bar" style="width:58%"></div></div>
        <div class="score-val">0.58</div>
      </div>
    </div>
  </div>
</section>

<!-- ── BUGS FIXED ── -->
<section class="fixes-section">
  <div class="section-eyebrow">Production fixes</div>
  <h2 class="section-title">The bugs that would have killed this in production.</h2>
  <p class="section-sub">None of these show up in tutorials.</p>

  <div class="fix-list">
    <div class="fix-item">
      <div class="fix-name">Thread-unsafe audio queue</div>
      <div class="fix-what">
        sounddevice fires mic_callback on its own OS thread.
        asyncio.Queue is not thread safe. Direct calls from that thread
        cause silent data corruption. Fixed with call_soon_threadsafe —
        the audio thread hands chunks to the event loop, never touches the queue itself.
      </div>
    </div>
    <div class="fix-item">
      <div class="fix-name">TTS completion sync</div>
      <div class="fix-what">
        Old code fired Speak() and returned instantly. Mic reopened mid-sentence.
        Bot transcribed its own voice as a new user question.
        Fixed with a unique stdout marker — mic only opens after the marker is seen.
      </div>
    </div>
    <div class="fix-item">
      <div class="fix-name">Infinite recursion</div>
      <div class="fix-what">
        Failed customer ID → back to intent classifier → back to ID handler → repeat forever.
        Fixed with a retry counter passed through every call. Escalates to human after 3 failures.
      </div>
    </div>
    <div class="fix-item">
      <div class="fix-name">listen_once hang</div>
      <div class="fix-what">
        In listen_once mode, receive() sat blocked inside async for with nothing to wake it.
        Fixed by racing all tasks with asyncio.wait FIRST_COMPLETED and explicitly cancelling
        whatever is still running when done fires.
      </div>
    </div>
    <div class="fix-item">
      <div class="fix-name">Circular imports</div>
      <div class="fix-what">
        llm_intent imports handlers. handlers need run_intent. Top-level import causes Python
        to get stuck mid-load. Fixed by importing run_intent inside the function body only,
        not at module level.
      </div>
    </div>
    <div class="fix-item">
      <div class="fix-name">LLM JSON parsing</div>
      <div class="fix-what">
        LLMs told to return only JSON sometimes wrap it in markdown fences or add a sentence.
        Raw json.loads crashes on this. Fixed with a shared safe_parse_json that strips fences
        and falls back to a safe default. Used everywhere.
      </div>
    </div>
  </div>
</section>

<!-- ── INDUSTRIES ── -->
<section class="industries-section">
  <div class="section-eyebrow">Beyond banking</div>
  <h2 class="section-title">The same pipeline. Any industry.</h2>
  <p class="section-sub">
    The core — multilingual STT, intent routing, RAG retrieval, TTS response —
    is domain-agnostic. Swap the knowledge base and DB schema. Everything else stays.
  </p>

  <div class="industry-grid">
    <div class="industry-card">
      <div class="industry-icon">🏥</div>
      <div class="industry-name">Healthcare</div>
      <div class="industry-value">Saves ₹ per agent hour</div>
      <div class="industry-desc">
        Appointment booking, prescription reminders, insurance query handling.
        Patients speak in local language. Agent understands and responds.
      </div>
    </div>
    <div class="industry-card">
      <div class="industry-icon">📦</div>
      <div class="industry-name">Logistics</div>
      <div class="industry-value">Zero hold time</div>
      <div class="industry-desc">
        Shipment tracking, delivery rescheduling, escalation to human for damaged goods.
        Works for delivery agents calling in Hindi or Telugu from the field.
      </div>
    </div>
    <div class="industry-card">
      <div class="industry-icon">🛒</div>
      <div class="industry-name">E-commerce</div>
      <div class="industry-value">24x7 without headcount</div>
      <div class="industry-desc">
        Order status, return requests, refund escalations.
        Handles the 80% of calls that are routine so human agents handle the 20% that matter.
      </div>
    </div>
    <div class="industry-card">
      <div class="industry-icon">🏛️</div>
      <div class="industry-name">Government Services</div>
      <div class="industry-value">Reaches Tier 2 and 3 cities</div>
      <div class="industry-desc">
        Scheme eligibility queries, document checklist, application status.
        Hindi and Telugu support is not a nice-to-have here — it is the only way to reach users.
      </div>
    </div>
    <div class="industry-card">
      <div class="industry-icon">📡</div>
      <div class="industry-name">Telecom</div>
      <div class="industry-value">Reduces churn calls</div>
      <div class="industry-desc">
        Plan details, data balance, recharge support, complaint escalation.
        The exact same call centre workflow this was built for.
      </div>
    </div>
    <div class="industry-card">
      <div class="industry-icon">🎓</div>
      <div class="industry-name">EdTech</div>
      <div class="industry-value">Scale without support team</div>
      <div class="industry-desc">
        Course queries, fee payment status, doubt escalation to tutors.
        Works for students calling from any state in their own language.
      </div>
    </div>
  </div>
</section>

<!-- ── FILE STRUCTURE ── -->
<section class="files-section">
  <div class="section-eyebrow">Codebase</div>
  <h2 class="section-title">What lives where.</h2>

  <div class="file-tree">
    <div><span class="ft-dir">llm_intent.py</span><span class="ft-desc">entry point · main loop · intent router</span></div>
    <div><span class="ft-dir">vachana_stt/</span></div>
    <div>&nbsp;&nbsp;<span class="ft-file">vachana.py</span><span class="ft-desc">mic input · STT streaming · TTS · silence detection · 20s timeout</span></div>
    <div><span class="ft-dir">handlers/</span></div>
    <div>&nbsp;&nbsp;<span class="ft-file">personal.py</span><span class="ft-desc">customer id extraction · DB lookup · account answers</span></div>
    <div>&nbsp;&nbsp;<span class="ft-file">general.py</span><span class="ft-desc">knowledge base search · policy answers</span></div>
    <div>&nbsp;&nbsp;<span class="ft-file">escalate.py</span><span class="ft-desc">ticket generation · staff handoff</span></div>
    <div>&nbsp;&nbsp;<span class="ft-file">smalltalk.py</span><span class="ft-desc">conversation reset · bot reintroduction</span></div>
    <div><span class="ft-dir">scripts/</span></div>
    <div>&nbsp;&nbsp;<span class="ft-file">queries.py</span><span class="ft-desc">DB functions · customer data fetch · id validation</span></div>
    <div><span class="ft-file">knowledge_base.py</span><span class="ft-desc">ChromaDB search · embedding · dynamic drop detection</span></div>
    <div><span class="ft-dir">utils/</span></div>
    <div>&nbsp;&nbsp;<span class="ft-file">utils.py</span><span class="ft-desc">safe JSON parser · markdown cleaner · shared helpers</span></div>
    <div><span class="ft-dir">connections/</span></div>
    <div>&nbsp;&nbsp;<span class="ft-file">connections.py</span><span class="ft-desc">API keys · DB connection · audio queue</span></div>
  </div>
</section>

<!-- ── TRADEOFFS ── -->
<section class="tradeoffs-section">
  <div class="section-eyebrow">Honest tradeoffs</div>
  <h2 class="section-title">What was chosen and what was not — and why.</h2>

  <div class="tradeoff-list">
    <div class="tradeoff-item">
      <div class="to-left">
        <div class="to-label">Skipped</div>
        OTP and email verification for customer identity
      </div>
      <div class="to-right">
        <div class="to-label">Reason</div>
        Out of scope for this version. Customer ID validation against DB is the current gate.
        OTP is on the roadmap.
      </div>
    </div>
    <div class="tradeoff-item">
      <div class="to-left">
        <div class="to-label">Skipped</div>
        Paid LLMs like GPT-4 or Claude Opus
      </div>
      <div class="to-right">
        <div class="to-label">Reason</div>
        LLaMA 3.1 8B on Groq is fast enough and free enough to run this at zero cost.
        No compromise on accuracy for classification tasks.
      </div>
    </div>
    <div class="tradeoff-item">
      <div class="to-left">
        <div class="to-label">Known gap</div>
        ChromaDB cold start adds a few seconds on first general query
      </div>
      <div class="to-right">
        <div class="to-label">Fix</div>
        Warming the knowledge base from startup regardless of query type.
        In progress.
      </div>
    </div>
    <div class="tradeoff-item">
      <div class="to-left">
        <div class="to-label">Known gap</div>
        Windows only TTS via PowerShell System.Speech
      </div>
      <div class="to-right">
        <div class="to-label">Fix</div>
        Vachana TTS integration in progress. Email sent to Gnani team.
        Will make the full stack platform agnostic.
      </div>
    </div>
  </div>
</section>

<!-- ── ROADMAP ── -->
<section class="roadmap-section">
  <div class="section-eyebrow">Where this is going</div>
  <h2 class="section-title">Done. Doing. Planned.</h2>

  <div class="roadmap-grid">
    <div class="roadmap-col col-done">
      <div class="roadmap-col-title">Done</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Voice pipeline end to end</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Intent classification in 4 languages</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Personal queries with DB lookup</div>
      <div class="roadmap-item"><div class="ri-dot"></div>RAG pipeline with drop detection</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Escalation with ticket generation</div>
      <div class="roadmap-item"><div class="ri-dot"></div>20 second silence timeout</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Error handling across all layers</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Conversation history and context</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Customer ID validation against DB</div>
    </div>
    <div class="roadmap-col col-doing">
      <div class="roadmap-col-title">In Progress</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Vachana TTS to replace Windows voice — email sent to Gnani, waiting for API access</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Response naturalness improvements — occasional over-talk still slips through</div>
      <div class="roadmap-item"><div class="ri-dot"></div>ChromaDB warm start on session begin</div>
    </div>
    <div class="roadmap-col col-planned">
      <div class="roadmap-col-title">Planned</div>
      <div class="roadmap-item"><div class="ri-dot"></div>FastAPI layer for deployment as a service</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Docker containerisation</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Structured call logging</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Latency and intent accuracy monitoring</div>
      <div class="roadmap-item"><div class="ri-dot"></div>OTP verification layer</div>
      <div class="roadmap-item"><div class="ri-dot"></div>Support for more Indian languages</div>
    </div>
  </div>
</section>

<!-- ── SETUP ── -->
<section class="setup-section">
  <div class="section-eyebrow">Get it running</div>
  <h2 class="section-title">Four steps.</h2>

  <div class="setup-steps">
    <div class="setup-step">
      <div class="step-num">1</div>
      <div class="step-body">
        <div class="step-title">Install dependencies</div>
        <pre>pip install sounddevice numpy groq chromadb sentence-transformers mysql-connector-python gnani-stt</pre>
      </div>
    </div>
    <div class="setup-step">
      <div class="step-num">2</div>
      <div class="step-body">
        <div class="step-title">Set up connections/connections.py with your API keys and DB credentials</div>
        <pre>VACHANA_API_KEY = "your_key"
groq_client    = groq.Groq(api_key="your_key")
db_conn        = mysql.connector.connect(...)</pre>
      </div>
    </div>
    <div class="setup-step">
      <div class="step-num">3</div>
      <div class="step-body">
        <div class="step-title">Build the knowledge base — run once, saves to disk</div>
        <pre>python knowledge_base.py</pre>
      </div>
    </div>
    <div class="setup-step">
      <div class="step-num">4</div>
      <div class="step-body">
        <div class="step-title">Start the agent</div>
        <pre>python llm_intent.py</pre>
      </div>
    </div>
  </div>
</section>

<!-- ── FOOTER ── -->
<footer class="footer">
  <div class="footer-name">Built by Nihar Nandala</div>
  <a class="footer-link" href="https://github.com/niharnandala/Banking_Voice_Agent_With_intelligent_Routing" target="_blank">
    github.com/niharnandala/Banking_Voice_Agent_With_intelligent_Routing
  </a>
</footer>

</body>
</html>
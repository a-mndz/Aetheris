export const SEED_CONVERSATIONS = [
  {
    id: "c1", title: "Should a startup prioritize MVP speed or correctness?",
    time: "7:02 PM", mode: "Balanced", agentsCount: 4, score: 92,
    transcript: [
      { role: "user", text: "Should a startup prioritize MVP speed or correctness?" },
      { role: "agent", agentId: "breaker", text: "Before answering \u2014 what counts as 'correctness' here? A payments flow and a marketing page don't share a bar." },
      { role: "agent", agentId: "logician", text: "Frame it as a cost curve: speed reduces time-to-signal, but rework cost compounds with every dependent feature built on a broken core." },
      { role: "agent", agentId: "creative", text: "A third option: ship fast on the parts users touch, hold the line on the parts that touch money or data." },
      { role: "agent", agentId: "judge", text: "Synthesis: prioritize speed everywhere except irreversible decisions \u2014 data models, auth, billing. Confidence 92%." },
    ],
  },
  {
    id: "c2", title: "Microservices vs Monolith for 10-person team",
    time: "6:45 PM", mode: "Deep", agentsCount: 3, score: 89,
    transcript: [
      { role: "user", text: "Compare microservices vs monolith architecture for a 10-person team." },
      { role: "agent", agentId: "logician", text: "10 engineers sits below the coordination threshold where service boundaries pay for themselves \u2014 Conway's Law works against you here." },
      { role: "agent", agentId: "breaker", text: "Counter: if you already know you're splitting by domain in 12 months, a modular monolith costs less to migrate later than untangling microservices costs now." },
      { role: "agent", agentId: "judge", text: "Synthesis: modular monolith, enforce module boundaries in code review, revisit at 25+ engineers. Confidence 89%." },
    ],
  },
  {
    id: "c3", title: "Fair way to split rent with unequal incomes",
    time: "5:20 PM", mode: "Balanced", agentsCount: 3, score: 85,
    transcript: [
      { role: "user", text: "Design a fair way to split rent between roommates with unequal incomes." },
      { role: "agent", agentId: "creative", text: "Split proportional to income, not equally \u2014 room size sets a base, income sets the delta on shared space." },
      { role: "agent", agentId: "judge", text: "Synthesis: base = room sqft ratio, adjustment = income ratio applied to shared spaces only. Confidence 85%." },
    ],
  },
  {
    id: "c4", title: "Trusting gut vs data in decision making",
    time: "Yesterday", mode: "Balanced", agentsCount: 3, score: 78,
    transcript: [
      { role: "user", text: "Is it rational to trust your gut over data when both disagree?" },
      { role: "agent", agentId: "breaker", text: "Depends what the 'gut' was trained on. An expert's intuition is compressed data; a novice's gut is noise." },
      { role: "agent", agentId: "judge", text: "Synthesis: weight gut higher only in-domain and under time pressure; weight data higher otherwise. Confidence 78%." },
    ],
  },
  {
    id: "c5", title: "Designing a scalable notification system",
    time: "Yesterday", mode: "Deep", agentsCount: 3, score: 91,
    transcript: [
      { role: "user", text: "How would you design a scalable notification system?" },
      { role: "agent", agentId: "logician", text: "Separate the write path (event ingestion) from the fan-out path (delivery) with a queue between them." },
      { role: "agent", agentId: "judge", text: "Synthesis: event bus \u2192 preference filter \u2192 per-channel workers \u2192 delivery log. Confidence 91%." },
    ],
  },
];

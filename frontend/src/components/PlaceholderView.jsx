import { FileText, Database, Blocks, Layers, Settings } from "lucide-react";

function PlaceholderView({ view }) {
  const copy = {
    templates: {
      title: "Templates",
      body: "No templates yet. Build one from a conversation that worked.",
      status: "Save a winning prompt + agent mix to reuse it.",
      icon: FileText,
    },
    knowledge: {
      title: "Knowledge base",
      body: "Empty. Drop documents here so agents can reference them.",
      status: "Attach .pdf, .md, or .txt to load source material.",
      icon: Database,
    },
    playground: {
      title: "Agent playground",
      body: "No custom agents. Adjust a prompt and response style to start.",
      status: "Tune one agent in isolation before adding it to a debate.",
      icon: Blocks,
    },
    integrations: {
      title: "Integrations",
      body: "No connections. Add a model provider to begin routing.",
      status: "BYO keys stay on your account; nothing is stored here.",
      icon: Layers,
    },
    settings: {
      title: "Settings",
      body: "Defaults are loaded. Adjust account and reasoning preferences here.",
      status: "Changes save automatically to your active session.",
      icon: Settings,
    },
  }[view];
  const Icon = copy.icon;
  return (
    <div className="placeholder">
      <div className="placeholder-mark" aria-hidden="true"><Icon size={32} /></div>
      <h2>{copy.title}</h2>
      <p>{copy.body}</p>
      <div className="placeholder-status">{copy.status}</div>
    </div>
  );
}

export default PlaceholderView;

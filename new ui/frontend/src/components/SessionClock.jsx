import { useState, useEffect } from "react";

const APP_START = Date.now();

export default function SessionClock() {
  const [elapsed, setElapsed] = useState(() => Math.floor((Date.now() - APP_START) / 1000));
  useEffect(() => {
    const iv = setInterval(() => setElapsed(Math.floor((Date.now() - APP_START) / 1000)), 1000);
    return () => clearInterval(iv);
  }, []);
  const hh = Math.floor(elapsed / 3600);
  const mm = String(Math.floor((elapsed % 3600) / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  return <span className="mono">{hh > 0 ? `${String(hh).padStart(2, "0")}:${mm}:${ss}` : `${mm}:${ss}`}</span>;
}

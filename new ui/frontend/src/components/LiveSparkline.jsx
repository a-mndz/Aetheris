import { useState, useEffect } from "react";
import Sparkline from "./Sparkline.jsx";

export default function LiveSparkline({ visible, data: externalData }) {
  const [data, setData] = useState(() => Array.from({ length: 24 }, () => 40 + Math.random() * 20));

  useEffect(() => {
    if (externalData && Array.isArray(externalData) && externalData.length > 0) {
      setData(externalData);
      return;
    }
    if (!visible) return;
    const iv = setInterval(() => {
      setData((d) => [...d.slice(1), Math.max(15, Math.min(80, d[d.length - 1] + (Math.random() - 0.5) * 18))]);
    }, 1800);
    return () => clearInterval(iv);
  }, [visible, externalData]);

  return <Sparkline data={externalData && externalData.length > 0 ? externalData : data} />;
}

import React, { useEffect, useState } from "react";
import { useJourney } from "../App.jsx";
import { api } from "../api/client.js";

// Order status view (section 2 module 4).
export default function Tracker() {
  const { journey } = useJourney();
  const [order, setOrder] = useState(null);
  const [id, setId] = useState(journey.orderId || "");

  async function load(oid) { try { setOrder(await api.getOrder(oid)); } catch {} }
  useEffect(() => { if (journey.orderId) { setId(journey.orderId); load(journey.orderId); } }, [journey.orderId]);

  async function advance() { if (order) setOrder(await api.advanceOrder(order.order_id)); }

  return (
    <div className="space-y-4">
      <div className="card flex gap-2">
        <input className="input" placeholder="ORD-XXXXXXXX" value={id}
               onChange={(e) => setId(e.target.value)} />
        <button className="btn" onClick={() => load(id)}>Track</button>
      </div>

      {order && (
        <div className="card">
          <div className="text-sm text-slate-500">Order {order.order_id}</div>
          <div className="text-xs text-slate-400 mb-4">
            Expected activation: {order.expected_activation}</div>
          <ol className="space-y-3">
            {order.stages.map((s, i) => {
              const done = i <= order.current_stage_index;
              return (
                <li key={s} className="flex items-center gap-3">
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs
                    ${done ? "bg-accel text-white" : "bg-slate-200 text-slate-400"}`}>
                    {done ? "✓" : i + 1}</span>
                  <span className={done ? "font-medium" : "text-slate-400"}>{s}</span>
                </li>);
            })}
          </ol>
          <button className="btn-ghost w-full mt-4" onClick={advance}>Simulate next stage →</button>
        </div>)}
    </div>
  );
}

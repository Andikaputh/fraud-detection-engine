import { Link, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { Analytics } from "./pages/Analytics";
import { Alerts } from "./pages/Alerts";
import { Model } from "./pages/Model";
import { Overview } from "./pages/Overview";
import { Settings } from "./pages/Settings";

function NotFound() {
  return (
    <div className="not-found">
      <span className="eyebrow">404</span>
      <h1>This route does not exist</h1>
      <p>The console has five surfaces: overview, alerts, analytics, model and settings.</p>
      <Link className="btn btn-primary" to="/">
        Return to overview
      </Link>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="model" element={<Model />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

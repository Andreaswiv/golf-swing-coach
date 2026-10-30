import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import AnalyseSwing from "./pages/AnalyseSwing";
import AnalysisResult from "./pages/AnalysisResult";
import Dashboard from "./pages/Dashboard";
import NotFound from "./pages/NotFound";
import Processing from "./pages/Processing";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="analyse" element={<AnalyseSwing />} />
        <Route path="analyses/:id/processing" element={<Processing />} />
        <Route path="analyses/:id" element={<AnalysisResult />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

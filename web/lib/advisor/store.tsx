"use client";
import {createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode} from "react";
import {callAdvisor} from "./client";
import type {AdvisorRequest, AdvisorResult, SourceCatalog} from "./contracts";

export const DEFAULT_REQUEST: AdvisorRequest = {journey: "idea", model_code: "G60", market: "US", powertrain: "ALL", model_year: 2026,
  question: "", ideas: [], objective: "Balanced customer value and business potential", planning_years: 3, currency: "EUR", budget: null};
function useStudioState() {
  const [request, setRequest] = useState(DEFAULT_REQUEST);
  const [constraints, setConstraints] = useState("");
  const [ideaText, setIdeaText] = useState("");
  const [catalog, setCatalog] = useState<SourceCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [result, setResult] = useState<AdvisorResult | null>(null);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<string[]>([]);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const refreshCatalog = useCallback(async () => {
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 15000);
    try {
      await callAdvisor("catalog", {}, (event) => { if (event.type === "catalog") setCatalog(event.catalog); }, abort.signal);
      setCatalogError("");
    } catch (e) {
      setCatalog(null);
      setCatalogError(abort.signal.aborted ? "Evidence check timed out. Check the database connection, then retry." : e instanceof Error ? e.message : "Evidence status could not be loaded.");
    } finally { clearTimeout(timeout); }
  }, []);
  useEffect(() => { void refreshCatalog(); }, [refreshCatalog]);
  async function run() {
    if (controller.current) return;
    const abort = new AbortController();
    controller.current = abort;
    setRunning(true); setError(""); setResult(null); setSteps([]);
    const payload = {...request, ideas: request.journey === "compare" ? ideaText.split("\n").map(s => s.trim()).filter(Boolean) : [],
      objective: request.objective + (constraints.trim() ? `. Constraints: ${constraints.trim()}` : "")};
    try {
      await callAdvisor("analyze", payload, (event) => {
        if (event.type === "progress") setSteps(previous => [...previous, event.message]);
        if (event.type === "result") setResult(event.result);
      }, abort.signal);
    } catch (e) {
      setError(abort.signal.aborted ? "Research stopped. No completed recommendation was generated." : e instanceof Error ? e.message : "Research could not finish.");
    } finally { controller.current = null; setRunning(false); void refreshCatalog(); }
  }
  function reset() { setResult(null); setSteps([]); setError(""); }
  return {request, setRequest, constraints, setConstraints, ideaText, setIdeaText, catalog, setCatalog, catalogError,
    refreshCatalog, result, setResult, running, steps, error, run, reset, stop: () => controller.current?.abort()};
}
const StudioContext = createContext<ReturnType<typeof useStudioState> | null>(null);
export function StudioProvider({children}: {children: ReactNode}) { return <StudioContext.Provider value={useStudioState()}>{children}</StudioContext.Provider>; }
export function useStudio() { const value = useContext(StudioContext); if (!value) throw new Error("StudioProvider is missing"); return value; }

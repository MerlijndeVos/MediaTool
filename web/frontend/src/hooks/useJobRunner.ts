import { useCallback, useRef, useState } from "react";
import { cancelJob, createJob, jobEventsUrl } from "@/api/client";
import type { ActiveJob, CommandName, LogLine } from "@/lib/types";

export function useJobRunner() {
  const [jobs, setJobs] = useState<ActiveJob[]>([]);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const sourcesRef = useRef<Map<string, EventSource>>(new Map());

  const appendLog = useCallback((line: LogLine) => {
    setLogs((prev) => [...prev.slice(-500), line]);
  }, []);

  const updateJob = useCallback((id: string, patch: Partial<ActiveJob>) => {
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, ...patch } : j)));
  }, []);

  const subscribe = useCallback(
    (jobId: string) => {
      const existing = sourcesRef.current.get(jobId);
      if (existing) existing.close();

      const es = new EventSource(jobEventsUrl(jobId));
      sourcesRef.current.set(jobId, es);

      es.addEventListener("log", (e) => {
        const data = JSON.parse(e.data) as { message: string; level: number };
        appendLog({ jobId, message: data.message, level: data.level, ts: Date.now() });
      });

      es.addEventListener("progress", (e) => {
        const data = JSON.parse(e.data) as {
          pct?: number | null;
          status?: string;
          title?: string;
        };
        const pct = data.pct ?? null;
        const label =
          data.title && pct != null
            ? `${data.title} — ${Math.round(pct)}%`
            : data.status ?? "Working…";
        updateJob(jobId, { progress: pct, progressLabel: label });
      });

      es.addEventListener("status", (e) => {
        const data = JSON.parse(e.data) as {
          status: ActiveJob["status"];
          error?: string;
        };
        updateJob(jobId, { status: data.status, error: data.error ?? null });
      });

      es.addEventListener("end", () => {
        es.close();
        sourcesRef.current.delete(jobId);
      });

      es.onerror = () => {
        es.close();
        sourcesRef.current.delete(jobId);
      };
    },
    [appendLog, updateJob],
  );

  const startJob = useCallback(
    async (command: CommandName, params: Record<string, unknown>, fileLogging = true) => {
      const res = await createJob(command, params, fileLogging);
      const job: ActiveJob = { ...res.job, logs: [], progress: null };
      setJobs((prev) => [job, ...prev]);
      appendLog({
        jobId: job.id,
        message: `=== Started ${command} (${job.id.slice(0, 8)}) ===`,
        level: 20,
        ts: Date.now(),
      });
      subscribe(job.id);
      return job;
    },
    [appendLog, subscribe],
  );

  const cancel = useCallback(async (jobId: string) => {
    await cancelJob(jobId);
    updateJob(jobId, { status: "cancelled" });
  }, [updateJob]);

  const clearLogs = useCallback(() => setLogs([]), []);

  return { jobs, logs, startJob, cancel, clearLogs };
}

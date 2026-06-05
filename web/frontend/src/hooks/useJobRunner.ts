import { useCallback, useRef, useState } from "react";
import { cancelJob, createJob, jobEventsUrl, undoRenameJob } from "@/api/client";
import type {
  ActiveJob,
  CommandName,
  DownloadProgress,
  LogLine,
  StartJobRequest,
} from "@/lib/types";

export function useJobRunner() {
  const [jobs, setJobs] = useState<ActiveJob[]>([]);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [undoing, setUndoing] = useState(false);
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
        const data = JSON.parse(e.data) as DownloadProgress & {
          pct?: number | null;
          status?: string;
          title?: string;
        };
        const pct = data.pct ?? null;
        const label =
          data.title && pct != null
            ? `${data.title} — ${Math.round(pct)}%`
            : data.status ?? "Working…";
        updateJob(jobId, {
          progress: pct,
          progressLabel: label,
          downloadProgress: {
            pct,
            downloaded: data.downloaded ?? null,
            total: data.total ?? null,
            speed: data.speed ?? null,
            eta: data.eta ?? null,
            status: data.status,
            title: data.title,
          },
        });
      });

      es.addEventListener("status", (e) => {
        const data = JSON.parse(e.data) as {
          status: ActiveJob["status"];
          error?: string;
          exit_code?: number | null;
          undo_available?: boolean;
          undo_used?: boolean;
          undo_op_count?: number | null;
          undo_source_job_id?: string;
          source_undo_used?: boolean;
        };
        updateJob(jobId, {
          status: data.status,
          error: data.error ?? null,
          exit_code: data.exit_code ?? null,
          undo_available: data.undo_available ?? false,
          undo_used: data.undo_used ?? false,
          undo_op_count: data.undo_op_count ?? null,
        });
        if (data.undo_source_job_id && data.source_undo_used) {
          updateJob(data.undo_source_job_id, {
            undo_used: true,
            undo_available: false,
          });
        }
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
    async (
      command: CommandName,
      params: Record<string, unknown>,
      fileLogging = true,
      opts?: Pick<StartJobRequest, "downloadMeta">,
    ) => {
      const res = await createJob(command, params, fileLogging);
      const job: ActiveJob = {
        ...res.job,
        logs: [],
        progress: null,
        downloadMeta: opts?.downloadMeta,
      };
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

  const startJobs = useCallback(
    async (command: CommandName, requests: StartJobRequest[], fileLogging = true) => {
      if (requests.length === 0) return;

      const placeholders: ActiveJob[] = requests.map((req) => ({
        id: `pending-${crypto.randomUUID()}`,
        command,
        status: "queued",
        created_at: new Date().toISOString(),
        logs: [],
        progress: null,
        downloadMeta: req.downloadMeta,
      }));

      setJobs((prev) => [...placeholders, ...prev]);

      await Promise.all(
        requests.map(async (req, index) => {
          const tempId = placeholders[index].id;
          try {
            const res = await createJob(command, req.params, fileLogging);
            const job: ActiveJob = {
              ...res.job,
              logs: [],
              progress: null,
              downloadMeta: req.downloadMeta,
            };
            setJobs((prev) => prev.map((j) => (j.id === tempId ? job : j)));
            appendLog({
              jobId: job.id,
              message: `=== Started ${command} (${job.id.slice(0, 8)}) ===`,
              level: 20,
              ts: Date.now(),
            });
            subscribe(job.id);
          } catch (e) {
            const message = e instanceof Error ? e.message : String(e);
            updateJob(tempId, { status: "failed", error: message });
          }
        }),
      );
    },
    [appendLog, subscribe, updateJob],
  );

  const cancel = useCallback(async (jobId: string) => {
    if (jobId.startsWith("pending-")) {
      setJobs((prev) => prev.filter((j) => j.id !== jobId));
      return;
    }
    await cancelJob(jobId);
    updateJob(jobId, { status: "cancelled" });
  }, [updateJob]);

  const clearLogs = useCallback(() => setLogs([]), []);

  const dismissFinishedDownloads = useCallback(() => {
    setJobs((prev) =>
      prev.filter(
        (j) =>
          j.command !== "download" ||
          (j.status !== "completed" && j.status !== "cancelled" && j.status !== "failed"),
      ),
    );
  }, []);

  const undoRename = useCallback(
    async (sourceJobId: string) => {
      setUndoing(true);
      try {
        const res = await undoRenameJob(sourceJobId);
        const job: ActiveJob = {
          ...res.job,
          logs: [],
          progress: null,
        };
        setJobs((prev) => [job, ...prev]);
        appendLog({
          jobId: job.id,
          message: `=== Undo rename (source ${sourceJobId.slice(0, 8)}) ===`,
          level: 20,
          ts: Date.now(),
        });
        subscribe(job.id);
      } finally {
        setUndoing(false);
      }
    },
    [appendLog, subscribe],
  );

  return {
    jobs,
    logs,
    startJob,
    startJobs,
    cancel,
    clearLogs,
    dismissFinishedDownloads,
    undoRename,
    undoing,
  };
}

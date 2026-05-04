import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export interface ComplaintRecord {
  id?: string;
  session_id?: string;
  timestamp: string;
  location: string | null;
  complaint_text?: string;
  issue?: string;
  urgency: number;
  status?: string;
  intent?: string | null;
  distress_level?: number;
  language?: string;
  acoustic_data?: {
    environment: string;
    loudness: string;
  };
}

function urgencyClass(urgency: number) {
  if (urgency >= 5) {
    return "bg-black text-white border-black";
  }
  if (urgency >= 3) {
    return "bg-black/80 text-white border-black";
  }
  return "bg-black/60 text-white border-black";
}

export function ComplaintsTable() {
  const [records, setRecords] = useState<ComplaintRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const initialFetchDone = useRef(false);

  const fetchComplaints = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("http://localhost:8000/api/complaints");
      if (!response.ok) {
        throw new Error(`Request failed with ${response.status}`);
      }
      const data = (await response.json()) as ComplaintRecord[];
      setRecords(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load complaints");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialFetchDone.current) {
      return;
    }
    initialFetchDone.current = true;
    void fetchComplaints();
  }, [fetchComplaints]);

  return (
    <Card className="border-black/10 bg-white">
      <CardContent className="p-0">
        <div className="px-6 py-4 border-b border-black/10 flex items-center justify-between">
          <div className="space-y-1">
            <h2 className="text-base font-semibold text-black">Records</h2>
            <p className="text-xs text-black/60">
              Confirmed complaints pending dispatch
            </p>
          </div>
          <Button
            variant="ghost"
            className="gap-2 cursor-pointer border border-black/15 text-black hover:text-black"
            onClick={() => void fetchComplaints()}
            disabled={loading}
          >
            <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        {error && (
          <div className="px-6 py-4 text-sm text-black bg-black/5 border-b border-black/10">
            {error}
          </div>
        )}

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Timestamp</TableHead>
              <TableHead>Session</TableHead>
              <TableHead>Location</TableHead>
              <TableHead>Issue</TableHead>
              <TableHead>Intent</TableHead>
              <TableHead>Urgency</TableHead>
              <TableHead>Distress</TableHead>
              <TableHead>Language</TableHead>
              <TableHead>Environment</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!loading && records.length === 0 && (
              <TableRow>
                <TableCell colSpan={10} className="text-center text-black/60 py-10">
                  No confirmed complaints yet.
                </TableCell>
              </TableRow>
            )}

            {records.map((record, index) => (
              <TableRow
                key={
                  record.id ||
                  record.session_id ||
                  `${record.timestamp}-${record.complaint_text || record.issue}-${index}`
                }
              >
                <TableCell className="whitespace-nowrap text-black/70">
                  {new Date(record.timestamp).toLocaleString()}
                </TableCell>
                <TableCell className="text-black/60">
                  {record.session_id || "—"}
                </TableCell>
                <TableCell>{record.location || "Unknown"}</TableCell>
                <TableCell className="max-w-[360px] text-black">
                  {record.complaint_text || record.issue || "—"}
                </TableCell>
                <TableCell className="text-black">
                  {record.intent || "—"}
                </TableCell>
                <TableCell>
                  <Badge className={urgencyClass(record.urgency)}>
                    {record.urgency}/5
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge className="bg-black/10 text-black border-black/20">
                    {record.distress_level ?? "—"}
                  </Badge>
                </TableCell>
                <TableCell className="text-black">
                  {record.language || "—"}
                </TableCell>
                <TableCell className="text-black">
                  {record.acoustic_data
                    ? `${record.acoustic_data.environment} · ${record.acoustic_data.loudness}`
                    : "—"}
                </TableCell>
                <TableCell>
                  <Badge className="bg-black text-white border-black">
                    {record.status || "Pending Dispatch"}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

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
  id: string;
  timestamp: string;
  location: string | null;
  issue: string;
  urgency: number;
  status: string;
}

function urgencyClass(urgency: number) {
  if (urgency >= 5) {
    return "bg-rose-500/15 text-rose-300 border-rose-500/30";
  }
  if (urgency >= 3) {
    return "bg-amber-500/15 text-amber-300 border-amber-500/30";
  }
  return "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
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
    <Card className="border-white/10 bg-white/[0.02]">
      <CardContent className="p-0">
        <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Records Dashboard</h2>
            <p className="text-xs text-muted-foreground">
              Confirmed complaints pending dispatch
            </p>
          </div>
          <Button
            variant="ghost"
            className="gap-2 cursor-pointer border border-white/10"
            onClick={() => void fetchComplaints()}
            disabled={loading}
          >
            <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        {error && (
          <div className="px-6 py-4 text-sm text-rose-300 bg-rose-500/10 border-b border-rose-500/10">
            {error}
          </div>
        )}

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Timestamp</TableHead>
              <TableHead>Location</TableHead>
              <TableHead>Issue</TableHead>
              <TableHead>Urgency</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!loading && records.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground py-10">
                  No confirmed complaints yet.
                </TableCell>
              </TableRow>
            )}

            {records.map((record) => (
              <TableRow key={record.id}>
                <TableCell className="whitespace-nowrap text-muted-foreground">
                  {new Date(record.timestamp).toLocaleString()}
                </TableCell>
                <TableCell>{record.location || "Unknown"}</TableCell>
                <TableCell className="max-w-[440px]">{record.issue}</TableCell>
                <TableCell>
                  <Badge className={urgencyClass(record.urgency)}>
                    {record.urgency}/5
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge className="bg-cyan-500/15 text-cyan-300 border-cyan-500/30">
                    {record.status}
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

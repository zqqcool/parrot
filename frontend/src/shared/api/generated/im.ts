// Generated contract mirror of backend/asyncapi/asyncapi.yaml. Do not edit in feature code.
export type ImEnvelope = {
  version: "1";
  type: string;
  message_id: string;
  request_id: string;
  interaction_id: string | null;
  sequence: number | null;
  occurred_at: string | null;
  data: Record<string, unknown>;
};

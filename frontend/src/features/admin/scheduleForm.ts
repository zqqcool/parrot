import type { Schedule, ScheduleCreate, ScheduleUpdate } from "@/shared/api/types";
import { toDateTimeLocalValue, toIsoDateTime } from "@/shared/time";

export type ScheduleForm = Omit<ScheduleCreate, "run_at"> & { run_at?: string };

export function toScheduleCreate(values: ScheduleForm): ScheduleCreate {
  return {
    ...values,
    cron_expr: values.schedule_type === "recurring" ? values.cron_expr : null,
    run_at: values.schedule_type === "once" && values.run_at ? toIsoDateTime(values.run_at) : null,
  };
}

export function toScheduleUpdate(values: ScheduleForm): ScheduleUpdate {
  const payload = toScheduleCreate(values);
  return {
    title: payload.title,
    input_text: payload.input_text,
    schedule_type: payload.schedule_type,
    cron_expr: payload.cron_expr,
    run_at: payload.run_at,
    timezone: payload.timezone,
  };
}

export function scheduleToForm(values: Schedule): ScheduleForm {
  return {
    agent_id: values.agent_id,
    schedule_type: values.schedule_type as ScheduleForm["schedule_type"],
    title: values.title,
    input_text: values.input_text,
    cron_expr: values.cron_expr,
    run_at: toDateTimeLocalValue(values.run_at),
    timezone: values.timezone,
  };
}

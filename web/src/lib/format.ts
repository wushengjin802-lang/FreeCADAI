export function formatShanghaiTime(value?: string | null) {
  if (!value) return "-";
  const source = String(value);
  // 如无时区信息则视为 UTC
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(source) ? source : `${source}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return source.replace("T", " ");

  // 转换为上海时间 (UTC+8)
  const shanghaiMs = date.getTime() + 8 * 60 * 60 * 1000;
  const d = new Date(shanghaiMs);
  const y = d.getUTCFullYear();
  const mo = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  const ss = String(d.getUTCSeconds()).padStart(2, "0");
  return `${y}-${mo}-${day} ${hh}:${mm}:${ss}`;
}

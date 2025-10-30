// helpers.js
export const MAX_MB = 25;

export function toCurrency(n) {
  try {
    return Number(n).toLocaleString(undefined, { style: "currency", currency: "USD" });
  } catch {
    return n;
  }
}

export const isPdf = (file) =>
  file && (file.type === "application/pdf" || /\.pdf$/i.test(file.name));

export const qs = (sel, root = document) => root.querySelector(sel);

export const toNum = (s) => Number(String(s ?? "").replace(/[^0-9.]/g, "")) || 0;

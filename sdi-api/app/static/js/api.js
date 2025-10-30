// api.js
async function postJSON(url, payload) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

async function postForm(url, formData) {
  const resp = await fetch(url, { method: "POST", body: formData });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export const PredictAPI = {
  predict: (payload) => postJSON("/predict", payload),
};

export const ExtractAPI = {
  extractCharges: (formData) => postForm("/extract-charges", formData),
  adjudicate: (payload) => postJSON("/adjudicate", payload),
};

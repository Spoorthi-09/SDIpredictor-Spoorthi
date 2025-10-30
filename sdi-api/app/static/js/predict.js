// predict.js
import { qs, toCurrency } from "./helper.js";
import { PredictAPI } from "./api.js";

export function initPredictStep() {
  const claimForm = qs("#claim-form");
  const resultBox = qs("#result");
  const resetBtn = qs("#reset-btn");
  const clipBox = qs("#clip");

  if (!(claimForm && resultBox && resetBtn && clipBox)) return;

  resetBtn.onclick = () => {
    claimForm.reset();
    resultBox.style.display = "none";
    resultBox.innerHTML = "";
  };

  claimForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const fd = new FormData(claimForm);
    const row = {};
    for (const [k, v] of fd.entries()) if (v !== "") row[k] = v;

    const payload = {
      rows: [row],
      clip_to_max_benefit: clipBox.checked,
    };

    resultBox.style.display = "block";
    resultBox.innerHTML = "<div class='muted'>Predicting…</div>";

    try {
      const data = await PredictAPI.predict(payload);
      const pred = Array.isArray(data.predictions)
        ? data.predictions[0]
        : data.predictions;

      resultBox.innerHTML = `
        <strong>Predicted Approved Benefit Amount:</strong> ${toCurrency(pred)}<br>
        <span class="muted">Clipped: ${data.clipped ? "Yes" : "No"}</span>
      `;
    } catch (err) {
      resultBox.innerHTML = `<span style="color:red;">Error: ${err.message}</span>`;
    }
  });
}


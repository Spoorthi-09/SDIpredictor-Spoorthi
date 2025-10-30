// upload.js
import { qs, isPdf, MAX_MB, toNum } from "./helper.js";
import { ExtractAPI } from "./api.js";

export function initUploadStep() {
  const container = qs("#fileInputs");
  const addBtn = qs("#addFileBtn");
  const moveoutForm = qs("#moveout-form");
  const extractResult = qs("#extract-result");

  if (!(container && addBtn && moveoutForm && extractResult)) return;

  // Add new file input row
  addBtn.addEventListener("click", () => {
    const row = document.createElement("div");
    row.className = "file-row";
    row.style.margin = "6px 0";
    row.innerHTML = `
      <input type="file" name="files" accept="application/pdf" />
      <button type="button" class="removeBtn" style="margin-left:6px;font-size:12px;">Remove</button>
    `;
    row.querySelector(".removeBtn").onclick = () => row.remove();
    container.appendChild(row);
  });

  function validateFiles() {
    const inputs = container.querySelectorAll('input[type="file"][name="files"]');
    const files = [];
    for (const inp of inputs) {
      if (inp.files && inp.files[0]) files.push(inp.files[0]);
    }
    if (!files.length) {
      alert("Upload at least one PDF");
      return null;
    }
    for (const f of files) {
      if (!isPdf(f)) {
        alert(`"${f.name}" is not a PDF.`);
        return null;
      }
      if (f.size > MAX_MB * 1024 * 1024) {
        alert(`"${f.name}" too large`);
        return null;
      }
    }
    return files;
  }

  moveoutForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const files = validateFiles();
    if (!files) return;

    extractResult.style.display = "block";
    extractResult.innerHTML = "<div class='muted'>Extracting charges…</div>";

    const formData = new FormData();
    const inputs = container.querySelectorAll('input[type="file"][name="files"]');
    for (const inp of inputs) {
      if (inp.files && inp.files[0]) {
        formData.append("files", inp.files[0], inp.files[0].name);
      }
    }

    try {
      const data = await ExtractAPI.extractCharges(formData);

      extractResult.style.display = "block";
      extractResult.innerHTML = `
        <div><strong>Charges Extracted:</strong></div>
        <pre class="charges-pre" style="white-space:pre-wrap;max-height:260px;overflow:auto;border:1px solid #e5e7eb;padding:8px;border-radius:8px;margin:6px 0;">
${JSON.stringify(
  data.charges?.length ? data.charges : data.charges_fallback || [],
  null,
  2
)}
        </pre>
        <div class="muted">LLM Used: ${data.llm_used ?? "N/A"}</div>
        <div style="margin-top:8px;">
          <button id="finalize-btn" type="button">Finalize Payout</button>
        </div>
      `;

      // Delegate clicks so handler survives re-render
      extractResult.addEventListener("click", async (evt) => {
        if (!(evt.target && evt.target.id === "finalize-btn")) return;

        const btn = evt.target;
        btn.disabled = true;
        const restore = () => {
          btn.disabled = false;
          btn.textContent = "Finalize Payout";
        };

        try {
          btn.textContent = "Finalizing…";

          const md = (data && data.metadata) || {};

          // Read UI fields
          const monthlyRentStr = qs('input[name="Monthly Rent"]')?.value || "";
          const maxBenefitStr  = qs('input[name="Max Benefit"]')?.value || "";
          const formMoveOutStr = qs('input[name="Move-Out Date"]')?.value || ""; // hyphen
          const leaseStateStr  = qs('input[name="Lease State"]')?.value || "";

          // Optional UI fields
          const depositAmountStr = qs('input[name="Deposit Amount"]')?.value || "";
          const jurisdictionStr  = qs('select[name="Jurisdiction"]')?.value || "";

          // Resolve deposit amount
          let depositAmountResolved = null;
          if (md.deposit_amount === "ONE_MONTH_RENT") {
            depositAmountResolved = toNum(monthlyRentStr) || null;
          } else if (typeof md.deposit_amount === "number") {
            depositAmountResolved = md.deposit_amount;
          } else {
            const uiDeposit = toNum(depositAmountStr);
            depositAmountResolved = uiDeposit > 0 ? uiDeposit : null;
          }

          // Resolve move-out date: prefer LLM > UI
          const moveOutResolved = md.move_out_date || formMoveOutStr || null;

          // Resolve jurisdiction: prefer LLM > explicit UI > lease state
          const jurisdictionResolved = md.jurisdiction || jurisdictionStr || leaseStateStr || null;

          // Charges chosen (LLM primary, fallback if empty)
          const llmCharges = Array.isArray(data.charges) && data.charges.length
            ? data.charges
            : data.charges_fallback || [];

          const adjudicatePayload = {
            tenant_name: "",
            property_address: "",

            monthly_rent: toNum(monthlyRentStr),
            max_benefit: toNum(maxBenefitStr),

            deposit_amount: depositAmountResolved,
            move_out_date: moveOutResolved,
            jurisdiction: jurisdictionResolved,

            documents_present: {
              lease_addendum: true,
              lease_agreement: true,
              notification_to_tenant: true,
              tenant_ledger: true,
              invoice: false,
              claim_evaluation_report: false,
            },
            ledger_checks: {
              first_month_rent_paid: true,
              first_month_rent_evidence: "",
              first_month_sdi_premium_paid: true,
              first_month_sdi_premium_paid_evidence: "",
            },
            charges: llmCharges,
          };

          const result2 = await ExtractAPI.adjudicate(adjudicatePayload);

          // Append result without clobbering button/handler
          const out = document.createElement("div");
          out.style.marginTop = "12px";
          out.classList.add("final-decision");
          out.innerHTML = `
            <div><strong>Final Decision</strong></div>
            <pre style="white-space:pre-wrap;max-height:260px;overflow:auto;border:1px solid #e5e7eb;padding:8px;border-radius:8px;margin:6px 0;">
${JSON.stringify(result2, null, 2)}
            </pre>
          `;

          const old = extractResult.querySelector(".final-decision");
          if (old) old.remove();
          extractResult.appendChild(out);

          btn.textContent = "Done";
        } catch (err) {
          alert("Finalize failed: " + (err.message || err));
          restore();
        }
      });
    } catch (err) {
      extractResult.innerHTML = `<span style="color:red;">Error: ${err.message}</span>`;
    }
  });
}

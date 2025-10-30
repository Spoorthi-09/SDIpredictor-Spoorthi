// main.js
import { initPredictStep } from "./predict.js";
import { initUploadStep } from "./upload.js";

document.addEventListener("DOMContentLoaded", () => {
  initPredictStep();
  initUploadStep();
});

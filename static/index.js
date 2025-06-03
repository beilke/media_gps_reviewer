// index.js - Shared/reusable JS for index.html (and optionally review.html)

document.addEventListener("DOMContentLoaded", function () {
  const modeScan = document.getElementById("modeScan");
  const modeCSV = document.getElementById("modeCSV");
  const scanGroup = document.getElementById("scanGroup");
  const csvGroup = document.getElementById("csvGroup");
  const scanDirectoryInput = document.getElementById("scan_directory");
  const csvFileInput = document.getElementById("csv_file");
  const findClosestGPS = document.getElementById("findClosestGPS");
  const timeFrameGroup = document.getElementById("timeFrameGroup");
  const timeFrameHours = document.getElementById("timeFrameHours");
  const unifiedForm = document.getElementById("unifiedForm");
  const scanResult = document.getElementById("scanResult");

  function updateMode() {
    if (modeScan.checked) {
      scanGroup.classList.remove("opacity-50", "pointer-events-none");
      scanDirectoryInput.disabled = false;
      document.getElementById("showWithGPS").disabled = false;
      findClosestGPS.disabled = false;
      timeFrameHours.disabled = !findClosestGPS.checked;
      csvGroup.classList.add("opacity-50", "pointer-events-none");
      csvFileInput.disabled = true;
    } else {
      scanGroup.classList.add("opacity-50", "pointer-events-none");
      scanDirectoryInput.disabled = true;
      document.getElementById("showWithGPS").disabled = true;
      findClosestGPS.disabled = true;
      timeFrameHours.disabled = true;
      csvGroup.classList.remove("opacity-50", "pointer-events-none");
      csvFileInput.disabled = false;
    }
  }

  modeScan.addEventListener("change", updateMode);
  modeCSV.addEventListener("change", updateMode);
  updateMode();

  if (findClosestGPS) {
    findClosestGPS.addEventListener("change", function () {
      timeFrameGroup.style.display = this.checked ? "" : "none";
      if (modeScan.checked) {
        timeFrameHours.disabled = !this.checked;
      }
    });
  }

  if (unifiedForm) {
    unifiedForm.addEventListener("submit", function (e) {
      e.preventDefault();
      scanResult.innerHTML = "";
      if (modeScan.checked) {
        // Scan Directory mode
        const directory = scanDirectoryInput.value.trim();
        if (!directory) {
          alert("Please enter a directory path to scan.");
          return;
        }
        const findClosest = findClosestGPS.checked;
        const timeFrame = findClosest ? parseInt(timeFrameHours.value, 10) : null;
        const showWithGPS = document.getElementById("showWithGPS").checked;
        scanResult.innerHTML =
          '<div class="text-center"><div class="spinner-border" role="status"></div> Scanning...</div>';
        fetch("/scan_directory", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            directory: directory,
            find_closest: findClosest,
            time_frame: timeFrame,
            show_with_gps: showWithGPS
          }),
        })
          .then((res) => res.json())
          .then((data) => {
            if (data.status === "success" && data.redirect) {
              window.location.href = data.redirect;
            } else if (data.status === "error") {
              scanResult.innerHTML = `<div class='alert alert-danger'>${
                data.message || "Scan failed."
              }</div>`;
            }
          })
          .catch((err) => {
            scanResult.innerHTML = `<div class='alert alert-danger'>Error: ${err.message}</div>`;
          });
      } else {
        // CSV Upload mode
        if (!csvFileInput.files.length) {
          alert("Please select a CSV file to upload.");
          return;
        }
        unifiedForm.submit();
      }
    });
  }
});

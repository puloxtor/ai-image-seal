/* Ghost Seal Desk — upload + queue polling. No framework, no build step. */
(function () {
  "use strict";

  var drop = document.getElementById("drop");
  var picker = document.getElementById("picker");
  var label = document.getElementById("drop-label");
  var flash = document.getElementById("flash");
  var queue = document.getElementById("queue");
  var title = document.getElementById("queue-title");
  if (!drop || !picker || !queue) return;

  function say(message) {
    if (!flash) return;
    if (!message) {
      flash.hidden = true;
      flash.textContent = "";
      return;
    }
    flash.hidden = false;
    flash.textContent = message;
  }

  function size(bytes) {
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB";
    if (bytes >= 1024) return Math.round(bytes / 1024) + " KB";
    return bytes + " B";
  }

  function cell(value, mono) {
    var td = document.createElement("td");
    if (mono) td.className = "gsd-mono";
    td.textContent = value == null || value === "" ? "—" : String(value);
    return td;
  }

  function render(payload) {
    var jobs = payload.jobs || [];
    var counts = payload.counts || {};
    var pending = (counts.queued || 0) + (counts.running || 0);

    if (title) {
      title.textContent = pending > 0
        ? pending + " file" + (pending === 1 ? "" : "s") + " being sealed"
        : "Everything handed over is sealed";
    }

    if (jobs.length === 0) {
      queue.innerHTML =
        '<p class="gsd-empty">Nothing here yet. Files you hand over appear with their measured relief as soon as the applier reports back.</p>';
      return;
    }

    var table = document.createElement("table");
    table.className = "gsd-table";
    table.innerHTML =
      "<thead><tr><th>File</th><th>Status</th><th>Mode</th><th>ΔL*</th>" +
      "<th>Correlation</th><th>Seal</th><th>Size</th><th>Sealed file</th></tr></thead>";
    var body = document.createElement("tbody");

    jobs.forEach(function (job) {
      var tr = document.createElement("tr");

      var name = document.createElement("td");
      name.className = "gsd-file";
      name.title = job.filename;
      name.textContent = job.filename;
      tr.appendChild(name);

      var status = document.createElement("td");
      var chip = document.createElement("span");
      chip.className = "gsd-chip gsd-mono";
      chip.setAttribute("data-status", job.status);
      chip.textContent = job.status;
      status.appendChild(chip);
      if (job.reason) {
        var reason = document.createElement("span");
        reason.style.cssText = "display:block;font-size:11px;color:var(--muted);margin-top:4px";
        reason.textContent = job.reason;
        status.appendChild(reason);
      }
      tr.appendChild(status);

      tr.appendChild(cell(job.relief_mode, true));
      tr.appendChild(cell(job.delta_l != null ? job.delta_l.toFixed(2) : null, true));
      tr.appendChild(cell(job.correlation != null ? job.correlation.toFixed(3) : null, true));
      tr.appendChild(cell(job.seal_geometry, true));
      tr.appendChild(cell(size(job.size || 0), true));

      var download = document.createElement("td");
      if (job.output_name) {
        var link = document.createElement("a");
        link.className = "gsd-dl gsd-mono";
        link.href = "/download/" + job.id;
        link.textContent = "download";
        download.appendChild(link);
      } else {
        download.className = "gsd-mono";
        download.style.color = "var(--muted)";
        download.textContent = "—";
      }
      tr.appendChild(download);

      body.appendChild(tr);
    });

    table.appendChild(body);
    queue.innerHTML = "";
    var scroller = document.createElement("div");
    scroller.style.overflowX = "auto";
    scroller.appendChild(table);
    queue.appendChild(scroller);
  }

  function poll() {
    fetch("/api/jobs", { headers: { accept: "application/json" } })
      .then(function (response) {
        if (response.status === 401) {
          window.location.reload();
          return null;
        }
        return response.ok ? response.json() : null;
      })
      .then(function (payload) {
        if (payload) render(payload);
      })
      .catch(function () {
        /* transient: the next tick picks it up */
      });
  }

  function send(files) {
    if (!files || files.length === 0) return;
    say("");
    label.textContent = "SENDING…";
    var form = new FormData();
    for (var i = 0; i < files.length; i += 1) form.append("files", files[i]);

    fetch("/upload", { method: "POST", body: form })
      .then(function (response) {
        return response.json().then(function (payload) {
          return { status: response.status, payload: payload };
        });
      })
      .then(function (result) {
        if (result.status === 401) {
          window.location.reload();
          return;
        }
        var payload = result.payload || {};
        if (!payload.ok) {
          say(payload.message || "The upload was refused.");
        } else if (payload.rejected && payload.rejected.length > 0) {
          say(
            "Queued " + (payload.accepted ? payload.accepted.length : 0) + ". Refused: " +
              payload.rejected
                .map(function (entry) {
                  return entry.filename + " (" + entry.reason + ")";
                })
                .join(", "),
          );
        }
        poll();
      })
      .catch(function () {
        say("The upload failed in transit.");
      })
      .then(function () {
        label.textContent = "DROP MASTERS HERE";
      });
  }

  drop.addEventListener("click", function () {
    picker.click();
  });
  drop.addEventListener("dragover", function (event) {
    event.preventDefault();
    drop.setAttribute("data-dragging", "true");
  });
  drop.addEventListener("dragleave", function () {
    drop.removeAttribute("data-dragging");
  });
  drop.addEventListener("drop", function (event) {
    event.preventDefault();
    drop.removeAttribute("data-dragging");
    if (event.dataTransfer && event.dataTransfer.files) send(event.dataTransfer.files);
  });
  picker.addEventListener("change", function () {
    send(picker.files);
    picker.value = "";
  });

  poll();
  window.setInterval(poll, 4000);
})();

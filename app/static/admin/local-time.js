// Format ISO UTC timestamps in the viewer's local timezone (admin UI).
(function () {
  "use strict";

  var MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];

  function formatTime12h(dt) {
    var hours = dt.getHours();
    var h12 = hours % 12 || 12;
    var minutes = String(dt.getMinutes()).padStart(2, "0");
    var ampm = hours < 12 ? "AM" : "PM";
    return h12 + ":" + minutes + " " + ampm;
  }

  function localDateKey(dt) {
    return (
      dt.getFullYear() +
      "-" +
      String(dt.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(dt.getDate()).padStart(2, "0")
    );
  }

  function formatRecordedAt(isoString, now) {
    var dt = new Date(isoString);
    if (isNaN(dt.getTime())) {
      return null;
    }

    now = now || new Date();
    var timeStr = formatTime12h(dt);
    var dtKey = localDateKey(dt);
    var nowKey = localDateKey(now);

    if (dtKey === nowKey) {
      return "Today " + timeStr;
    }

    var yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (dtKey === localDateKey(yesterday)) {
      return "Yesterday " + timeStr;
    }

    var datePart = MONTHS[dt.getMonth()] + " " + dt.getDate();
    if (dt.getFullYear() !== now.getFullYear()) {
      datePart += ", " + dt.getFullYear();
    }
    return datePart + " · " + timeStr;
  }

  function applyLocalTimes(root) {
    var nodes = (root || document).querySelectorAll("time[datetime]");
    nodes.forEach(function (el) {
      var iso = el.getAttribute("datetime");
      if (!iso) {
        return;
      }
      var formatted = formatRecordedAt(iso);
      if (formatted) {
        el.textContent = formatted;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      applyLocalTimes();
    });
  } else {
    applyLocalTimes();
  }
})();

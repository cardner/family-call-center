// Browser-based prompt preview on the Settings page.
//
// Live IVR calls use the Twilio Neural2 voice selected in the dropdown. The
// browser cannot use those voices, so preview approximates the result with the
// Web Speech API: it matches the selected voice's language and gender to a local
// voice, and interprets the allowed SSML subset (break/emphasis/prosody) so
// pacing roughly reflects what callers hear.
(function () {
  "use strict";

  var synth = window.speechSynthesis;

  var voiceSelect = document.getElementById("ivr_voice");
  var voiceMeta = {};
  var metaEl = document.getElementById("ivr-voice-meta");
  if (metaEl) {
    try {
      voiceMeta = JSON.parse(metaEl.textContent) || {};
    } catch (e) {
      voiceMeta = {};
    }
  }

  var RATE_WORDS = {
    "x-slow": 0.6,
    slow: 0.85,
    medium: 1.0,
    fast: 1.15,
    "x-fast": 1.4,
  };

  // Generation counter: bumping it invalidates any in-flight utterance chain so
  // a new preview (or a second click) cleanly supersedes the previous one.
  var generation = 0;

  function clampRate(value) {
    return Math.max(0.5, Math.min(2.0, value));
  }

  function parseBreakMs(timeAttr) {
    if (!timeAttr) {
      return 250;
    }
    var match = /^(\d+(?:\.\d+)?)(ms|s)$/i.exec(timeAttr.trim());
    if (!match) {
      return 250;
    }
    var amount = parseFloat(match[1]);
    return match[2].toLowerCase() === "s" ? amount * 1000 : amount;
  }

  function parseRate(rateAttr) {
    if (!rateAttr) {
      return 1.0;
    }
    var value = rateAttr.trim().toLowerCase();
    if (RATE_WORDS[value] !== undefined) {
      return RATE_WORDS[value];
    }
    var percent = /^(\d+)%$/.exec(value);
    if (percent) {
      return parseInt(percent[1], 10) / 100;
    }
    return 1.0;
  }

  function getAttr(tagBody, name) {
    var re = new RegExp(name + '\\s*=\\s*["\']([^"\']*)["\']', "i");
    var match = re.exec(tagBody);
    return match ? match[1] : "";
  }

  // Walk the prompt text and produce a flat list of segments:
  //   { type: "text", text, rate, volume } | { type: "break", ms }
  // Rate/volume context nests via a stack so <prosody> and <emphasis> combine.
  function parseSegments(text) {
    var segments = [];
    var rateStack = [1.0];
    var volumeStack = [1.0];
    var pos = 0;
    var buffer = "";

    function currentRate() {
      return rateStack.reduce(function (a, b) {
        return a * b;
      }, 1.0);
    }
    function currentVolume() {
      return volumeStack[volumeStack.length - 1];
    }
    function flush() {
      if (buffer.trim()) {
        segments.push({
          type: "text",
          text: buffer.replace(/\s+/g, " ").trim(),
          rate: clampRate(currentRate()),
          volume: currentVolume(),
        });
      }
      buffer = "";
    }

    while (pos < text.length) {
      var ch = text[pos];
      if (ch !== "<") {
        buffer += ch;
        pos += 1;
        continue;
      }

      var end = text.indexOf(">", pos);
      if (end === -1) {
        buffer += text.slice(pos);
        break;
      }

      var raw = text.slice(pos + 1, end).trim();
      pos = end + 1;
      var lower = raw.toLowerCase();

      if (lower.indexOf("break") === 0) {
        flush();
        segments.push({ type: "break", ms: parseBreakMs(getAttr(raw, "time")) });
      } else if (lower.indexOf("emphasis") === 0) {
        flush();
        // Slightly slower reads as more emphatic; keep full volume.
        rateStack.push(0.92);
        volumeStack.push(1.0);
      } else if (lower.indexOf("/emphasis") === 0) {
        flush();
        if (rateStack.length > 1) rateStack.pop();
        if (volumeStack.length > 1) volumeStack.pop();
      } else if (lower.indexOf("prosody") === 0) {
        flush();
        rateStack.push(parseRate(getAttr(raw, "rate")));
        volumeStack.push(currentVolume());
      } else if (lower.indexOf("/prosody") === 0) {
        flush();
        if (rateStack.length > 1) rateStack.pop();
        if (volumeStack.length > 1) volumeStack.pop();
      }
      // Unknown tags are dropped, mirroring the server-side SSML whitelist.
    }

    flush();
    return segments;
  }

  function pickVoice(meta) {
    var voices = synth.getVoices() || [];
    var lang = (meta && meta.lang) || "en-US";
    var gender = (meta && meta.gender) || "";
    var langPrefix = lang.slice(0, 2).toLowerCase();

    var localeMatches = voices.filter(function (voice) {
      return voice.lang && voice.lang.toLowerCase().replace("_", "-").indexOf(lang.toLowerCase()) === 0;
    });
    var candidates = localeMatches.length
      ? localeMatches
      : voices.filter(function (voice) {
          return voice.lang && voice.lang.toLowerCase().indexOf(langPrefix) === 0;
        });

    if (!candidates.length) {
      return null;
    }

    if (gender) {
      var genderRe = gender === "female" ? /female|woman|zira|samantha|victoria|karen|fiona|moira|tessa/i : /male|man|david|daniel|alex|fred|rishi|oliver/i;
      var genderMatch = candidates.find(function (voice) {
        return genderRe.test(voice.name);
      });
      if (genderMatch) {
        return genderMatch;
      }
    }

    return candidates[0];
  }

  function resetButton(button, label) {
    button.disabled = false;
    button.textContent = label;
  }

  function playSegments(segments, meta, button, label) {
    var myGeneration = generation;
    var voice = pickVoice(meta);
    var lang = (meta && meta.lang) || "en-US";
    var index = 0;

    function finish() {
      if (myGeneration === generation) {
        resetButton(button, label);
      }
    }

    function next() {
      if (myGeneration !== generation) {
        return;
      }
      if (index >= segments.length) {
        finish();
        return;
      }
      var segment = segments[index];
      index += 1;

      if (segment.type === "break") {
        window.setTimeout(next, segment.ms);
        return;
      }

      if (!segment.text) {
        next();
        return;
      }

      var utterance = new SpeechSynthesisUtterance(segment.text);
      utterance.lang = lang;
      if (voice) {
        utterance.voice = voice;
      }
      utterance.rate = segment.rate;
      utterance.volume = segment.volume;
      utterance.onend = next;
      utterance.onerror = function () {
        if (myGeneration === generation) {
          resetButton(button, label);
          window.alert("Could not play preview audio.");
        }
      };
      synth.speak(utterance);
    }

    button.textContent = "Playing…";
    next();
  }

  function handlePreview(button, label) {
    var fieldId = button.getAttribute("data-field");
    var textarea = fieldId ? document.getElementById(fieldId) : null;
    if (!textarea) {
      return;
    }

    var text = textarea.value.trim();
    if (!text) {
      window.alert("Enter some prompt text to preview.");
      return;
    }

    // Supersede any in-flight preview before starting a new one.
    generation += 1;
    synth.cancel();

    var selectedVoice = voiceSelect ? voiceSelect.value : "";
    var meta = voiceMeta[selectedVoice] || {};
    var segments = parseSegments(text);
    if (!segments.length) {
      return;
    }

    playSegments(segments, meta, button, label);
  }

  document.querySelectorAll(".prompt-preview-btn").forEach(function (button) {
    var label = button.textContent;

    if (!synth || typeof window.SpeechSynthesisUtterance === "undefined") {
      button.disabled = true;
      button.title = "Preview is not supported in this browser.";
      return;
    }

    button.addEventListener("click", function () {
      handlePreview(button, label);
    });
  });

  // Some browsers populate the voice list asynchronously; touch it early so the
  // first preview has voices available.
  if (synth && typeof synth.getVoices === "function") {
    synth.getVoices();
    if (typeof synth.addEventListener === "function") {
      synth.addEventListener("voiceschanged", function () {
        synth.getVoices();
      });
    }
  }
})();

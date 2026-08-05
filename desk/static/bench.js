/* Visibility bench — the pinned mask pressed into a ground, live.
 *
 * PREVIEW ONLY. It shares the mask, the CIELAB luminance-only relief and the
 * mode-selection rule with the applier, but every real seal this service issues
 * is applied by the Python applier in the same container. Never treat this
 * canvas as the production stamp. */
(function () {
  "use strict";

  var canvas = document.getElementById("bench");
  var slider = document.getElementById("delta");
  var grounds = document.getElementById("grounds");
  if (!canvas || !slider || !grounds) return;

  var STAGE = 300;
  var SEAL = 244;
  var FLAT = { paper: "#f2f1ec", white: "#ffffff", black: "#000000" };
  var state = { ground: "paper", delta: parseFloat(slider.value) || 5, maps: null, size: 0 };

  var D65 = [0.95047, 1.0, 1.08883];

  function fwd(t) {
    return t > 0.008856451679035631 ? Math.cbrt(t) : t / 0.12841854934601665 + 4 / 29;
  }
  function inv(t) {
    return t > 6 / 29 ? t * t * t : 0.12841854934601665 * (t - 4 / 29);
  }
  function toLinear(c) {
    var v = c / 255;
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  }
  function fromLinear(v) {
    var c = v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(Math.max(v, 0), 1 / 2.4) - 0.055;
    return Math.max(0, Math.min(255, c * 255));
  }
  function rgbToLab(r, g, b) {
    var rl = toLinear(r), gl = toLinear(g), bl = toLinear(b);
    var x = (0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl) / D65[0];
    var y = (0.2126729 * rl + 0.7151522 * gl + 0.072175 * bl) / D65[1];
    var z = (0.0193339 * rl + 0.119192 * gl + 0.9503041 * bl) / D65[2];
    var fx = fwd(x), fy = fwd(y), fz = fwd(z);
    return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
  }
  function labToRgb(L, a, bb) {
    var fy = (L + 16) / 116, fx = fy + a / 500, fz = fy - bb / 200;
    var x = inv(fx) * D65[0], y = inv(fy) * D65[1], z = inv(fz) * D65[2];
    return [
      fromLinear(3.2404542 * x - 1.5371385 * y - 0.4985314 * z),
      fromLinear(-0.969266 * x + 1.8760108 * y + 0.041556 * z),
      fromLinear(0.0556434 * x - 0.2040259 * y + 1.0572252 * z),
    ];
  }

  function normalise(map) {
    var peak = 0, i;
    for (i = 0; i < map.length; i += 1) peak = Math.max(peak, Math.abs(map[i]));
    if (peak === 0) return map;
    for (i = 0; i < map.length; i += 1) map[i] /= peak;
    return map;
  }

  function buildMaps(mask, size, offset) {
    var n = size * size;
    var bipolar = new Float32Array(n), press = new Float32Array(n), emboss = new Float32Array(n);
    var gamma = 0.55;
    function at(x, y) {
      if (x < 0 || y < 0 || x >= size || y >= size) return 0;
      return mask[y * size + x];
    }
    for (var y = 0; y < size; y += 1) {
      for (var x = 0; x < size; x += 1) {
        var i = y * size + x;
        var m = mask[i], hi = at(x + offset, y + offset), sh = at(x - offset, y - offset);
        bipolar[i] = 1.15 * 0.8 * hi - 0.92 * sh - 0.34 * m;
        var mg = Math.pow(m, gamma), shg = Math.pow(sh, gamma), hig = Math.pow(hi, gamma);
        press[i] = -(0.75 * shg + 0.85 * mg);
        emboss[i] = 0.75 * hig + 0.85 * mg;
      }
    }
    return {
      size: size,
      bipolar: normalise(bipolar),
      press: normalise(press),
      emboss: normalise(emboss),
    };
  }

  function lossFraction(data, map, delta) {
    var ink = 0, lost = 0;
    for (var i = 0, p = 0; i < map.length; i += 1, p += 4) {
      var d = delta * map[i];
      if (Math.abs(d) <= 0.15) continue;
      ink += 1;
      var L = rgbToLab(data[p], data[p + 1], data[p + 2])[0];
      var achieved = Math.max(0, Math.min(100, L + d)) - L;
      if (Math.abs(d) - Math.abs(achieved) > 0.5 * Math.abs(d)) lost += 1;
    }
    return ink === 0 ? 1 : lost / ink;
  }

  function meanLightness(data) {
    var total = 0, count = 0;
    for (var p = 0; p < data.length; p += 28) {
      total += rgbToLab(data[p], data[p + 1], data[p + 2])[0];
      count += 1;
    }
    return count === 0 ? 50 : total / count;
  }

  function render() {
    if (!state.maps) return;
    var dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
    var stagePx = Math.round(STAGE * dpr);
    var sealPx = state.maps.size;
    var inset = Math.max(0, Math.round((stagePx - sealPx) / 2));

    canvas.width = stagePx;
    canvas.height = stagePx;
    var ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = FLAT[state.ground] || FLAT.paper;
    ctx.fillRect(0, 0, stagePx, stagePx);

    var patch = ctx.getImageData(inset, inset, sealPx, sealPx);
    var data = patch.data;

    var mode = "bipolar";
    var delta = state.delta;
    if (lossFraction(data, state.maps.bipolar, delta) > 0.02) {
      mode = meanLightness(data) >= 50 ? "press" : "emboss";
      delta = state.delta * 1.2;
    }
    var map = state.maps[mode];

    var maxDL = 0, sumDL = 0, inkPixels = 0;
    for (var i = 0, p = 0; i < map.length; i += 1, p += 4) {
      var d = delta * map[i];
      if (Math.abs(d) < 0.02) continue;
      var lab = rgbToLab(data[p], data[p + 1], data[p + 2]);
      var factor = 1, rgb = [0, 0, 0];
      for (var attempt = 0; attempt < 6; attempt += 1) {
        var target = Math.max(0, Math.min(100, lab[0] + d * factor));
        rgb = labToRgb(target, lab[1], lab[2]);
        var out = rgb[0] <= 0.001 || rgb[0] >= 254.999 || rgb[1] <= 0.001 ||
                  rgb[1] >= 254.999 || rgb[2] <= 0.001 || rgb[2] >= 254.999;
        var clipped = Math.abs(target - lab[0]) < Math.abs(d * factor) - 0.001;
        if (!out && !clipped) break;
        factor *= 0.5;
      }
      var applied = Math.abs(Math.max(0, Math.min(100, lab[0] + d * factor)) - lab[0]);
      if (applied > 0.05) {
        maxDL = Math.max(maxDL, applied);
        sumDL += applied;
        inkPixels += 1;
      }
      data[p] = rgb[0];
      data[p + 1] = rgb[1];
      data[p + 2] = rgb[2];
    }
    ctx.putImageData(patch, inset, inset);

    document.getElementById("stat-mode").textContent = mode;
    document.getElementById("stat-max").textContent = maxDL.toFixed(2);
    document.getElementById("stat-mean").textContent =
      (inkPixels === 0 ? 0 : sumDL / inkPixels).toFixed(2);
  }

  var image = new Image();
  image.onload = function () {
    var dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
    var sealPx = Math.round(SEAL * dpr);
    var scratch = document.createElement("canvas");
    scratch.width = sealPx;
    scratch.height = sealPx;
    var sctx = scratch.getContext("2d");
    if (!sctx) return;
    sctx.drawImage(image, 0, 0, sealPx, sealPx);
    var pixels = sctx.getImageData(0, 0, sealPx, sealPx).data;
    var mask = new Float32Array(sealPx * sealPx);
    for (var i = 0, p = 0; i < mask.length; i += 1, p += 4) mask[i] = pixels[p] / 255;
    state.maps = buildMaps(mask, sealPx, Math.max(1, Math.round(dpr)));
    render();
  };
  image.src = "/static/seal-master.png";

  slider.addEventListener("input", function () {
    state.delta = parseFloat(slider.value);
    document.getElementById("delta-value").textContent = state.delta.toFixed(1) + " L*";
    render();
  });

  grounds.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-ground]");
    if (!button) return;
    state.ground = button.getAttribute("data-ground");
    Array.prototype.forEach.call(grounds.querySelectorAll("button"), function (other) {
      if (other === button) other.setAttribute("data-active", "true");
      else other.removeAttribute("data-active");
    });
    document.getElementById("ground-value").textContent = button.textContent.trim();
    render();
  });
})();

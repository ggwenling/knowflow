"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

const vertexShader = `
  uniform float uTime;
  uniform float uPixelRatio;
  uniform float uWidth;
  varying float vOpacity;

  float bell(float x, float center, float width) {
    float distance = (x - center) / width;
    return exp(-distance * distance);
  }

  void main() {
    float depth = position.y;
    float t = uTime;
    // The rows converge into the distance; the near rows spread out naturally.
    float perspective = pow(depth, 1.65);
    float x = (position.x - .5) * mix(.88, 1.16, depth) + .5;
    x += .017 * sin(depth * 5.8 + x * 6.0 + t * .22) * depth;
    float left = bell(x, .055 + .023 * sin(t * .24 + depth * 1.8), .19);
    float center = bell(x, .565 + .035 * sin(t * .19 - depth * 1.6), .135);
    float right = bell(x, 1.035 + .028 * cos(t * .21 + depth), .225);
    float ridges = .92 * left + .35 * center + .88 * right;
    float y = .55 + .65 * perspective - ridges * mix(.50, .45, depth);
    y += .035 * sin(x * 10.5 + depth * 5.0 - t * .32) * depth;
    y += .015 * sin(x * 20.0 - depth * 3.0 + t * .24) * depth;

    gl_Position = vec4(x * 2.0 - 1.0, 1.0 - y * 2.0, 0.0, 1.0);
    float size = mix(.7, 3.1, pow(depth, 1.2));
    gl_PointSize = size * uPixelRatio * clamp(uWidth / 1200.0, .72, 1.18);

    float horizonFade = smoothstep(.015, .32, depth);
    float bottomFade = 1.0 - smoothstep(.65, 1.02, y);
    float edgeFade = smoothstep(-.06, .025, x) * (1.0 - smoothstep(.98, 1.06, x));
    vOpacity = mix(.055, .44, pow(depth, .75)) * horizonFade * bottomFade * edgeFade;
  }
`;

const fragmentShader = `
  varying float vOpacity;
  void main() {
    float radius = length(gl_PointCoord - vec2(.5));
    float coverage = 1.0 - smoothstep(.24, .5, radius);
    if (coverage < .01) discard;
    gl_FragColor = vec4(vec3(.38), coverage * vOpacity);
  }
`;

export default function HomeWave() {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = host.current;
    if (!element) return;

    const canvas = document.createElement("canvas");
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false, powerPreference: "low-power" });
    } catch {
      return;
    }
    renderer.setClearColor(0xffffff, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;

    const scene = new THREE.Scene();
    const camera = new THREE.Camera();
    const geometry = new THREE.BufferGeometry();
    // Interleave both axes so small screens retain the full surface with fewer dots.
    const columns = 240;
    const rows = 64;
    const positions = new Float32Array(columns * rows * 3);
    let offset = 0;
    for (let rowPass = 0; rowPass < 2; rowPass++) {
      for (let columnPass = 0; columnPass < 2; columnPass++) {
        for (let row = rowPass; row < rows; row += 2) {
          for (let column = columnPass; column < columns; column += 2) {
            positions[offset++] = (column + (row % 2) * .35) / (columns - 1);
            positions[offset++] = row / (rows - 1);
            positions[offset++] = 0;
          }
        }
      }
    }
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const uniforms = {
      uTime: { value: 0 },
      uPixelRatio: { value: 1 },
      uWidth: { value: 1200 },
    };
    const material = new THREE.ShaderMaterial({
      uniforms, vertexShader, fragmentShader, transparent: true,
      depthTest: false, depthWrite: false,
    });
    const points = new THREE.Points(geometry, material);
    points.frustumCulled = false;
    scene.add(points);

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let previousTime = 0;
    let elapsed = 0;
    let visible = true;
    let contextLost = false;
    let disposed = false;

    function render(now: number) {
      frame = 0;
      if (disposed || contextLost || !visible || document.hidden) return;
      // Clamp resumed frames, keeping the wave continuous after tab changes.
      if (previousTime) elapsed += Math.min((now - previousTime) / 1000, .05);
      previousTime = now;
      uniforms.uTime.value = reducedMotion.matches ? 0 : elapsed;
      renderer.render(scene, camera);
      if (!reducedMotion.matches) frame = requestAnimationFrame(render);
    }
    function restart() {
      cancelAnimationFrame(frame);
      frame = 0;
      previousTime = 0;
      render(performance.now());
    }
    function resize() {
      if (disposed || contextLost) return;
      const width = element!.clientWidth;
      const height = element!.clientHeight;
      if (!width || !height) return;
      const compact = width < 700;
      const ratio = Math.min(window.devicePixelRatio || 1, compact ? 1.5 : 2);
      renderer.setPixelRatio(ratio);
      renderer.setSize(width, height, false);
      uniforms.uPixelRatio.value = ratio;
      uniforms.uWidth.value = width;
      geometry.setDrawRange(0, columns * rows / (compact ? 4 : 1));
      restart();
    }
    function onContextLost(event: Event) {
      event.preventDefault();
      contextLost = true;
      cancelAnimationFrame(frame);
      // Removing the canvas reveals the static image until WebGL recovers.
      canvas.remove();
    }
    function onContextRestored() {
      contextLost = false;
      element!.appendChild(canvas);
      resize();
    }

    canvas.addEventListener("webglcontextlost", onContextLost);
    canvas.addEventListener("webglcontextrestored", onContextRestored);
    element.appendChild(canvas);
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(element);
    const intersectionObserver = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      restart();
    });
    intersectionObserver.observe(element);
    reducedMotion.addEventListener("change", restart);
    document.addEventListener("visibilitychange", restart);
    resize();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      reducedMotion.removeEventListener("change", restart);
      document.removeEventListener("visibilitychange", restart);
      canvas.removeEventListener("webglcontextlost", onContextLost);
      canvas.removeEventListener("webglcontextrestored", onContextRestored);
      scene.remove(points);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      canvas.remove();
    };
  }, []);

  return <div className="home-wave" ref={host} aria-hidden="true" />;
}

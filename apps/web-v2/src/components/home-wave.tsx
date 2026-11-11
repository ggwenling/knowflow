"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

const STRANDS = 40;
const SEGMENTS = 160;
const PARTICLES = 1200;

// Shared by the filaments and their travelling fragments, so every fragment
// follows its thread. Coordinates describe an open loom, pinched into one answer.
const flowShader = /* glsl */ `
  uniform float uTime;
  uniform vec2 uViewport;
  uniform vec2 uResolution;
  uniform float uPixelRatio;
  uniform float uMobile;
  uniform vec4 uComposer;
  uniform vec4 uScope;
  uniform vec4 uWordmark;
  uniform vec3 uInk;
  uniform vec3 uAccent;

  float focus(float t) {
    float d = (t - .82) / .13;
    return exp(-d * d);
  }

  vec3 flow(float t, float lane) {
    float gather = focus(t);
    float spread = mix(.30, .045, gather);
    float twist = t * 3.3 - .7;
    float x = mix(-.08, 1.08, t);
    // A broad arch recedes behind the wordmark, then turns toward the answer.
    // Mobile lifts the entire arch, rather than compressing it under the input.
    float y = mix(.48 - .23 * sin(t * 6.283185 - .6),
                  .34 - .16 * sin(t * 6.283185 - .7), uMobile);
    y += lane * spread * cos(twist);
    y += .007 * sin(t * 9.0 + lane * 2.0 - uTime * .20) * (1.0 - gather);
    float z = lane * .95 * sin(twist) - .22 + .18 * cos(t * 3.141593);
    z += .06 * sin(t * 6.0 - uTime * .13) * (1.0 - gather);
    return vec3((x - .5) * uViewport.x, (.5 - y) * uViewport.y, z);
  }

  float controlClearance(vec2 pixel, vec4 bounds) {
    vec2 d = abs(pixel - bounds.xy) - bounds.zw;
    float distance = length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
    return smoothstep(0.0, 38.0, distance);
  }

  float paperFade(vec3 p) {
    // Mask in projected CSS pixels, so foreground strands also clear controls.
    vec4 clip = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
    vec2 screen = vec2(clip.x / clip.w * .5 + .5, .5 - clip.y / clip.w * .5);
    vec2 pixel = screen * uResolution;
    float edge = smoothstep(.0, .09, screen.x) * (1.0 - smoothstep(.93, 1.0, screen.x));
    edge *= smoothstep(.02, .16, screen.y) * (1.0 - smoothstep(.84, 1.0, screen.y));
    float textDistance = length((pixel - uWordmark.xy) / uWordmark.zw);
    float textFade = mix(.055, 1.0, smoothstep(.65, 1.5, textDistance));
    float controls = controlClearance(pixel, uComposer) * controlClearance(pixel, uScope);
    float inputTop = uComposer.y - uComposer.w;
    float mobileFade = 1.0 - smoothstep(inputTop - 46.0, inputTop - 10.0, pixel.y);
    return edge * textFade * controls * mix(1.0, mobileFade, uMobile);
  }
`;

const filamentVertex = /* glsl */ `
  ${flowShader}
  varying float vAcross;
  varying float vOpacity;
  varying float vAccent;

  void main() {
    float t = position.x;
    float lane = position.y;
    vec3 p = flow(t, lane);
    vec3 next = flow(t + .001, lane);
    vec4 clip = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
    vec4 nextClip = projectionMatrix * modelViewMatrix * vec4(next, 1.0);
    vec2 tangent = normalize((nextClip.xy / nextClip.w - clip.xy / clip.w) * uResolution);
    vec2 normal = vec2(-tangent.y, tangent.x);
    float front = smoothstep(-1.15, .85, p.z);
    float width = mix(.24, .90, front);
    clip.xy += normal * position.z * width * 2.0 / uResolution * clip.w;
    gl_Position = clip;
    vAcross = position.z;
    float pulse = pow(.5 + .5 * sin(t * 15.0 - uTime * .65 + lane * 3.0), 8.0);
    vOpacity = paperFade(p) * (mix(.035, .30, front) + pulse * .045);
    vOpacity *= 1.0 - focus(t) * .55;
    vAccent = step(.94, sin(lane * 19.0));
  }
`;

const filamentFragment = /* glsl */ `
  uniform vec3 uInk;
  uniform vec3 uAccent;
  varying float vAcross;
  varying float vOpacity;
  varying float vAccent;

  void main() {
    float coverage = 1.0 - smoothstep(.30, 1.0, abs(vAcross));
    gl_FragColor = vec4(mix(uInk, uAccent, vAccent * .65), vOpacity * coverage);
    #include <colorspace_fragment>
  }
`;

const particleVertex = /* glsl */ `
  ${flowShader}
  varying float vOpacity;
  varying float vKind;
  varying float vAccent;

  void main() {
    // z = 0: flowing fragments, 1: source/retrieval nodes, 2: answer seal.
    float kind = position.z;
    float speed = .026 * (1.0 + .12 * sin(position.y * 7.0));
    float t = kind < .5 ? fract(position.x + uTime * speed) : position.x;
    vec3 p = flow(t, position.y);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
    float front = smoothstep(-1.15, .85, p.z);
    float size = mix(1.7, 4.2, front) * (.8 + .2 * sin(position.x * 617.0));
    if (kind > .5) size = kind > 1.5 ? mix(36.0, 26.0, uMobile) : 13.0;
    gl_PointSize = size * uPixelRatio;
    vOpacity = paperFade(p) * mix(.12, .62, front);
    if (kind > .5) vOpacity = paperFade(p) * .65;
    else vOpacity *= 1.0 - smoothstep(.82, 1.0, t) * .65;
    vKind = kind;
    vAccent = kind > 1.5 ? 1.0 : step(.94, sin(position.y * 19.0));
  }
`;

const particleFragment = /* glsl */ `
  uniform vec3 uInk;
  uniform vec3 uAccent;
  varying float vOpacity;
  varying float vKind;
  varying float vAccent;

  void main() {
    vec2 p = gl_PointCoord - .5;
    float r = length(p);
    float aa = max(fwidth(r), .012);
    float alpha;
    if (vKind > 1.5) {
      // A precise iris with a soft centre: cheap local glow, no bloom buffers.
      float ring = 1.0 - smoothstep(aa * .5, aa * 1.5, abs(r - .29));
      float core = 1.0 - smoothstep(.045, .095, r);
      float halo = exp(-r * r * 26.0) * .12;
      alpha = ring * .65 + core + halo;
    } else if (vKind > .5) {
      // Sparse, consistently sized retrieval points with a fine circular rim.
      float ring = 1.0 - smoothstep(aa * .5, aa * 1.5, abs(r - .26));
      float core = 1.0 - smoothstep(.025, .11, r);
      alpha = ring * .55 + core * .55 + exp(-r * r * 18.0) * .10;
    } else {
      float core = 1.0 - smoothstep(.035, .20, r);
      float halo = exp(-r * r * 18.0) * .20 * (1.0 - smoothstep(.38, .5, r));
      alpha = core + halo;
    }
    gl_FragColor = vec4(mix(uInk, uAccent, vAccent), min(alpha, 1.0) * vOpacity);
    #include <colorspace_fragment>
  }
`;

function makeFilaments() {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(STRANDS * (SEGMENTS + 1) * 6);
  const indices = new Uint16Array(STRANDS * SEGMENTS * 6);
  let vertex = 0;
  let index = 0;
  for (let strand = 0; strand < STRANDS; strand++) {
    // Even/odd lanes are interleaved so halving the draw range on mobile
    // retains the entire silhouette, with no geometry rebuild on resize.
    const lane = ((strand % (STRANDS / 2)) * 2 + Math.floor(strand / (STRANDS / 2))) / (STRANDS - 1) * 2 - 1;
    for (let step = 0; step <= SEGMENTS; step++) {
      const base = vertex / 3;
      for (const side of [-1, 1]) {
        positions[vertex++] = step / SEGMENTS;
        positions[vertex++] = lane;
        positions[vertex++] = side;
      }
      if (step < SEGMENTS) {
        indices.set([base, base + 2, base + 1, base + 2, base + 3, base + 1], index);
        index += 6;
      }
    }
  }
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(new THREE.BufferAttribute(indices, 1));
  return geometry;
}

function makeParticles() {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(PARTICLES * 3);
  for (let i = 0; i < PARTICLES; i++) {
    // Low-discrepancy seeds give a repeatable still, with no startup clumps.
    positions[i * 3] = (i * .61803398875) % 1;
    positions[i * 3 + 1] = (i % STRANDS) / (STRANDS - 1) * 2 - 1;
  }
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  return geometry;
}

function makeNodes() {
  const geometry = new THREE.BufferGeometry();
  // The answer is first so mobile retains it alongside two retrieval points.
  const positions = [
    .82, 0, 2,
    .12, -.9, 1,
    .61, .8, 1,
    .26, .65, 1,
    .44, -.5, 1,
    .91, -.65, 1,
  ];
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return geometry;
}

export default function HomeWave({ paused = false }: { paused?: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(paused);
  useEffect(() => {
    pausedRef.current = paused;
    host.current?.dispatchEvent(new Event("motionchange"));
  }, [paused]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;

    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false, powerPreference: "low-power" });
    } catch {
      return;
    }
    renderer.setClearColor(0xf5f0e6, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, .1, 30);
    camera.position.z = 7;
    const tokens = getComputedStyle(element);
    const hero = element.closest(".home-art")?.parentElement?.parentElement
      ?.querySelector<HTMLElement>('[aria-labelledby="home-title"]');
    const uniforms = {
      uTime: { value: 0 },
      uPixelRatio: { value: 1 },
      uResolution: { value: new THREE.Vector2(1200, 400) },
      uViewport: { value: new THREE.Vector2() },
      uMobile: { value: 0 },
      uComposer: { value: new THREE.Vector4(-10000, -10000, 1, 1) },
      uScope: { value: new THREE.Vector4(-10000, -10000, 1, 1) },
      uWordmark: { value: new THREE.Vector4(600, 140, 240, 65) },
      uInk: { value: new THREE.Color(tokens.getPropertyValue("--ink-2").trim() || "#575249") },
      uAccent: { value: new THREE.Color(tokens.getPropertyValue("--accent").trim() || "#ad402c") },
    };
    const filamentGeometry = makeFilaments();
    const particleGeometry = makeParticles();
    const nodeGeometry = makeNodes();
    const filamentMaterial = new THREE.ShaderMaterial({
      uniforms, vertexShader: filamentVertex, fragmentShader: filamentFragment,
      transparent: true, depthTest: false, depthWrite: false, blending: THREE.NormalBlending,
    });
    const particleMaterial = new THREE.ShaderMaterial({
      uniforms, vertexShader: particleVertex, fragmentShader: particleFragment,
      transparent: true, depthTest: false, depthWrite: false, blending: THREE.NormalBlending,
    });
    const filaments = new THREE.Mesh(filamentGeometry, filamentMaterial);
    const particles = new THREE.Points(particleGeometry, particleMaterial);
    const nodes = new THREE.Points(nodeGeometry, particleMaterial);
    // The GPU computes positions; CPU bounds describe only path parameters.
    filaments.frustumCulled = particles.frustumCulled = nodes.frustumCulled = false;
    filaments.renderOrder = 0;
    particles.renderOrder = 1;
    nodes.renderOrder = 2;
    scene.add(filaments, particles, nodes);

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let previousTime = 0;
    let elapsed = 0;
    let visible = false;
    let contextLost = false;
    let disposed = false;

    function render(now: number) {
      frame = 0;
      if (disposed || contextLost || !visible || document.hidden) return;
      // Clamp resumed frames, keeping the flow continuous after tab changes.
      if (previousTime && !pausedRef.current) elapsed += Math.min((now - previousTime) / 1000, .05);
      previousTime = now;
      uniforms.uTime.value = reducedMotion.matches ? 0 : elapsed;
      renderer.render(scene, camera);
      if (!reducedMotion.matches && !pausedRef.current) frame = requestAnimationFrame(render);
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
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      const viewHeight = 2 * camera.position.z * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
      uniforms.uViewport.value.set(viewHeight * camera.aspect, viewHeight);
      uniforms.uResolution.value.set(width, height);
      uniforms.uPixelRatio.value = ratio;
      uniforms.uMobile.value = window.innerWidth <= 760 ? 1 : 0;
      // Layout reads happen only on resize (including hero height changes when
      // the selector appears). The render loop updates just the time uniform.
      const hostBounds = element!.getBoundingClientRect();
      function measureControl(control: Element | null | undefined, target: THREE.Vector4) {
        if (!control) {
          target.set(-10000, -10000, 1, 1);
          return;
        }
        const bounds = control.getBoundingClientRect();
        target.set(bounds.x + bounds.width / 2 - hostBounds.x,
          bounds.y + bounds.height / 2 - hostBounds.y, bounds.width / 2 + 14, bounds.height / 2 + 12);
      }
      measureControl(hero?.querySelector("form"), uniforms.uComposer.value);
      measureControl(hero?.querySelector("label"), uniforms.uScope.value);
      const title = hero?.querySelector("h1");
      if (title) {
        const titleBounds = title.getBoundingClientRect();
        const leadBounds = title.nextElementSibling?.getBoundingClientRect() ?? titleBounds;
        const textHeight = leadBounds.bottom - titleBounds.top;
        uniforms.uWordmark.value.set(titleBounds.x + titleBounds.width / 2 - hostBounds.x,
          titleBounds.top + textHeight / 2 - hostBounds.y, Math.min(width * .29, 245), textHeight * .55);
      }
      filamentGeometry.setDrawRange(0, STRANDS * SEGMENTS * 6 / (compact ? 2 : 1));
      particleGeometry.setDrawRange(0, compact ? 400 : PARTICLES);
      nodeGeometry.setDrawRange(0, compact ? 3 : 6);
      restart();
    }
    function onContextLost(event: Event) {
      event.preventDefault();
      contextLost = true;
      cancelAnimationFrame(frame);
      // The :has(canvas) fallback switches back to the static artwork.
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
    if (hero) resizeObserver.observe(hero);
    const intersectionObserver = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      restart();
    });
    intersectionObserver.observe(element);
    reducedMotion.addEventListener("change", restart);
    element.addEventListener("motionchange", restart);
    document.addEventListener("visibilitychange", restart);
    resize();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      reducedMotion.removeEventListener("change", restart);
      element.removeEventListener("motionchange", restart);
      document.removeEventListener("visibilitychange", restart);
      canvas.removeEventListener("webglcontextlost", onContextLost);
      canvas.removeEventListener("webglcontextrestored", onContextRestored);
      scene.clear();
      filamentGeometry.dispose();
      particleGeometry.dispose();
      nodeGeometry.dispose();
      filamentMaterial.dispose();
      particleMaterial.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    };
  }, []);

  return <div className="home-wave" ref={host} aria-hidden="true" />;
}

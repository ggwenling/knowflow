"use client";
import { useEffect, useRef } from 'react';
import { BufferGeometry, Camera, Float32BufferAttribute, LineSegments, Scene, ShaderMaterial, Vector2, WebGLRenderer } from "three";

export default function Flow({ paused = false }: { paused?: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(paused);
  useEffect(() => {
    pausedRef.current = paused;
    host.current?.toggleAttribute("data-motion-paused", paused);
    host.current?.dispatchEvent(new Event("motionchange"));
  }, [paused]);
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let renderer: WebGLRenderer;
    try {
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("webgl2", { alpha: true, antialias: true });
      if (!context) return;
      renderer = new WebGLRenderer({ canvas, context, alpha: true, antialias: true });
    } catch {
      return;
    }

    const scene = new Scene();
    const camera = new Camera();
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
    const compact = window.matchMedia('(max-width: 700px)');
    const segments = 180;
    const vertices: number[] = [];
    // Even strands come first so mobile can draw half the lines across the same surface.
    for (let index = 0; index < 84; index++) {
      const strand = (index % 42) * 2 + Math.floor(index / 42);
      const v = strand / 83 * 2 - 1;
      for (let step = 0; step < segments; step++) {
        vertices.push(step / segments, v, 0, (step + 1) / segments, v, 0);
      }
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new Float32BufferAttribute(vertices, 3));
    const uniforms = {
      time: { value: 0 },
      pointer: { value: new Vector2() },
    };
    const material = new ShaderMaterial({
      uniforms,
      transparent: true,
      depthWrite: false,
      vertexShader: `
        uniform float time;
        uniform vec2 pointer;
        varying float ink;
        void main() {
          float u = position.x;
          float v = position.y;
          float phase = u * 8.5 + time;
          float twist = 1.3 + u * 6.8 + .22 * sin(time + u * 4.);
          float width = mix(.14, .39, smoothstep(.06, .82, u));
          float depth = v * sin(twist) * width;
          float lift = -.77 + 1.51 * u + .27 * sin(phase - .6);
          float y = lift + v * cos(twist) * width + .08 * v * v;
          float x = mix(-1.04, 1.16, u) + .17 * depth;
          x += pointer.x * (.24 + depth);
          y += pointer.y * (.32 + depth);
          gl_Position = vec4(x, y, 0., 1.);
          float fade = smoothstep(.0, .25, u) * (1. - smoothstep(.91, 1., u));
          ink = fade * (.075 + .105 * smoothstep(-.22, .22, depth));
        }
      `,
      fragmentShader: `
        varying float ink;
        void main() {
          gl_FragColor = vec4(vec3(.32), ink);
        }
      `,
    });
    const ribbon = new LineSegments(geometry, material);
    ribbon.frustumCulled = false;
    scene.add(ribbon);
    el.appendChild(renderer.domElement);

    const target = new Vector2();
    let frame = 0;
    let previous: number | undefined;
    let visible = false;
    let contextLost = false;
    let disposed = false;
    let compiled = false;
    let compilation = 0;
    let bounds = el.getBoundingClientRect();
    const draw = (now: number) => {
      frame = 0;
      if (disposed || !compiled || contextLost || !visible || document.hidden) return;
      const dt = previous === undefined ? 0 : Math.min((now - previous) / 1000, .05);
      previous = now;
      if (reduce.matches) {
        uniforms.time.value = 0;
        uniforms.pointer.value.set(0, 0);
      } else if (!pausedRef.current) {
        uniforms.time.value += dt * .28;
        uniforms.pointer.value.lerp(target, 1 - Math.exp(-dt * 3));
      }
      renderer.render(scene, camera);
      if (renderer.domElement.dataset.sceneReady !== "true") renderer.domElement.dataset.sceneReady = "true";
      if (!reduce.matches && !pausedRef.current) frame = requestAnimationFrame(draw);
    };
    const resize = () => {
      if (disposed || contextLost) return;
      bounds = el.getBoundingClientRect();
      const width = el.clientWidth;
      const height = el.clientHeight;
      if (!width || !height) return;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, compact.matches ? 1.5 : 2));
      renderer.setSize(width, height, false);
      geometry.setDrawRange(0, (compact.matches ? 42 : 84) * segments * 2);
      restart();
    };
    const reset = () => target.set(0, 0);
    const move = (event: PointerEvent) => {
      const rect = bounds;
      if (event.pointerType !== 'mouse' || event.clientX < rect.left || event.clientX > rect.right ||
          event.clientY < rect.top || event.clientY > rect.bottom) {
        reset();
        return;
      }
      target.set((event.clientX - rect.left) / rect.width - .5,
        .5 - (event.clientY - rect.top) / rect.height).multiplyScalar(.28);
    };
    const restart = () => {
      cancelAnimationFrame(frame);
      previous = undefined;
      draw(performance.now());
    };

    async function prepare() {
      const token = ++compilation;
      try {
        await renderer.compileAsync(scene, camera);
        if (disposed || contextLost || token !== compilation) return;
        compiled = true;
        restart();
      } catch {
        if (!disposed && token === compilation) renderer.domElement.remove();
      }
    }

    const canvas = renderer.domElement;
    canvas.setAttribute("aria-hidden", "true");
    const lost = (event: Event) => {
      event.preventDefault();
      contextLost = true;
      compiled = false;
      compilation++;
      delete canvas.dataset.sceneReady;
      cancelAnimationFrame(frame);
      canvas.remove();
    };
    const restored = () => { contextLost = false; el.appendChild(canvas); resize(); void prepare(); };
    const updateBounds = () => { bounds = el.getBoundingClientRect(); };
    const observer = new ResizeObserver(resize);
    const intersection = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; restart(); });
    observer.observe(el);
    intersection.observe(el);
    canvas.addEventListener('webglcontextlost', lost);
    canvas.addEventListener('webglcontextrestored', restored);
    document.addEventListener('visibilitychange', restart);
    window.addEventListener('scroll', updateBounds, { capture: true, passive: true });
    resize();
    void prepare();
    window.addEventListener('pointermove', move, { passive: true });
    document.documentElement.addEventListener('pointerleave', reset);
    reduce.addEventListener('change', restart);
    el.addEventListener('motionchange', restart);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      intersection.disconnect();
      canvas.removeEventListener('webglcontextlost', lost);
      canvas.removeEventListener('webglcontextrestored', restored);
      document.removeEventListener('visibilitychange', restart);
      window.removeEventListener('scroll', updateBounds, true);
      window.removeEventListener('pointermove', move);
      document.documentElement.removeEventListener('pointerleave', reset);
      reduce.removeEventListener('change', restart);
      el.removeEventListener('motionchange', restart);
      geometry.dispose();
      material.dispose();
      scene.clear();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, []);
  return <div className="loginCanvas" ref={host} aria-hidden="true" />;
}

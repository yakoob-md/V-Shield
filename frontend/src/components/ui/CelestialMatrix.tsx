import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

const CelestialMatrix: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // 1) Scene, camera, clock
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const clock = new THREE.Clock();

    // 2) Renderer
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(window.devicePixelRatio);
      container.appendChild(renderer.domElement);
    } catch (err) {
      console.error('WebGL not supported:', err);
      container.innerHTML = 
        '<p style="color:white;text-align:center;">Sorry, your browser does not support WebGL.</p>';
      return;
    }

    // 3) Shaders
    const vertexShader = `
      void main() {
        gl_Position = vec4(position, 1.0);
      }
    `;

    const fragmentShader = `
      precision highp float;
      uniform vec2 iResolution;
      uniform float iTime;
      uniform vec2 iMouse;

      float random(vec2 st) {
        return fract(sin(dot(st.xy, vec2(12.9898, 78.233))) * 43758.5453123);
      }

      void main() {
        // normalize coords by height
        vec2 uv = (gl_FragCoord.xy * 2.0 - iResolution.xy) / iResolution.y;
        vec2 mouse = (iMouse * 2.0 - iResolution) / iResolution.y;

        float dist = length(uv - mouse);
        float warp = smoothstep(0.5, 0.0, dist);
        uv += normalize(uv - mouse) * warp * 0.2;

        float gridSize = 50.0; // Higher density
        vec2 gridUv = fract(uv * gridSize);
        vec2 gridId = floor(uv * gridSize);

        float t = iTime * 1.5;
        float rainSpeed = 0.4;
        float fall = fract(gridId.y * 0.05 - t * rainSpeed + random(gridId.xx) * 5.0);

        float character = random(gridId + floor(t * 8.0 * random(gridId.yx)));
        character = step(0.98, character);

        float glow = 1.0 - smoothstep(0.0, 0.5, gridUv.y);
        float intensity = character * glow * fall;

        // Vivid Light Blue / Deep Ocean accents
        vec3 color1 = vec3(0.0, 0.45, 0.74); // Deep Ocean Blue light variant
        vec3 color2 = vec3(0.4, 0.8, 0.9);   // Sky Blue
        vec3 finalColor = mix(color1, color2, random(gridId)) * intensity;

        gl_FragColor = vec4(finalColor, 0.15); // Very subtle for white theme transparency
      }
    `;

    // 4) Uniforms, material, mesh
    const uniforms = {
      iTime:       { value: 0 },
      iResolution: { value: new THREE.Vector2() },
      iMouse:      { value: new THREE.Vector2() }
    };
    const material = new THREE.ShaderMaterial({ 
      vertexShader, 
      fragmentShader, 
      uniforms,
      transparent: true 
    });
    const geometry = new THREE.PlaneGeometry(2, 2);
    const mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);

    // 5) Resize handler
    const onResize = () => {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      renderer.setSize(w, h);
      uniforms.iResolution.value.set(w, h);
    };
    window.addEventListener('resize', onResize);
    onResize();

    // 6) Mouse handler
    const onMouseMove = (e: MouseEvent) => {
      uniforms.iMouse.value.set(e.clientX, container.clientHeight - e.clientY);
    };
    window.addEventListener('mousemove', onMouseMove);

    // 7) Animation loop
    renderer.setAnimationLoop(() => {
      uniforms.iTime.value = clock.getElapsedTime();
      renderer.render(scene, camera);
    });

    // 8) Cleanup
    return () => {
      window.removeEventListener('resize', onResize);
      window.removeEventListener('mousemove', onMouseMove);
      renderer.setAnimationLoop(null);
      if (renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement);
      }
      material.dispose();
      geometry.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-0 pointer-events-none opacity-40"
      aria-hidden="true"
    />
  );
};

export default CelestialMatrix;

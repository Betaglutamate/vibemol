import {
  AmbientLight,
  Color,
  DirectionalLight,
  InstancedMesh,
  Matrix4,
  Object3D,
  PerspectiveCamera,
  Scene,
  SphereGeometry,
  MeshStandardMaterial,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import type { SphereGeometry as SphereData } from "../protocol/types";

// The Phase 0 renderer: an instanced-sphere viewport with an orbit camera.
// The camera lives entirely here (client-owned) so interaction never
// round-trips to the server. Phase 1 swaps the InstancedMesh for GPU impostor
// spheres/cylinders and adds picking, but the public surface stays the same.
export class Viewer {
  private readonly scene = new Scene();
  private readonly camera: PerspectiveCamera;
  private readonly renderer: WebGLRenderer;
  private readonly controls: OrbitControls;
  private spheres: InstancedMesh | null = null;

  constructor(private readonly container: HTMLElement) {
    this.scene.background = new Color(0x0b0d10);

    const { clientWidth: w, clientHeight: h } = container;
    this.camera = new PerspectiveCamera(45, w / h, 0.1, 5000);
    this.camera.position.set(0, 0, 30);

    this.renderer = new WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setSize(w, h);
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;

    this.scene.add(new AmbientLight(0xffffff, 0.55));
    const key = new DirectionalLight(0xffffff, 0.9);
    key.position.set(1, 1, 1);
    this.scene.add(key);

    window.addEventListener("resize", this.onResize);
    this.animate();
  }

  /** Replace the rendered atoms with a new sphere geometry set. */
  setSpheres(data: SphereData): void {
    if (this.spheres) {
      this.scene.remove(this.spheres);
      this.spheres.geometry.dispose();
      (this.spheres.material as MeshStandardMaterial).dispose();
      this.spheres = null;
    }

    const unit = new SphereGeometry(1, 24, 16);
    const material = new MeshStandardMaterial({ roughness: 0.4, metalness: 0.0 });
    const mesh = new InstancedMesh(unit, material, data.nAtoms);

    const dummy = new Object3D();
    const color = new Color();
    const m = new Matrix4();
    for (let i = 0; i < data.nAtoms; i++) {
      const r = data.radii[i];
      dummy.position.set(
        data.positions[i * 3],
        data.positions[i * 3 + 1],
        data.positions[i * 3 + 2],
      );
      dummy.scale.setScalar(r);
      dummy.updateMatrix();
      m.copy(dummy.matrix);
      mesh.setMatrixAt(i, m);
      color.setRGB(data.colors[i * 3], data.colors[i * 3 + 1], data.colors[i * 3 + 2]);
      mesh.setColorAt(i, color);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;

    this.scene.add(mesh);
    this.spheres = mesh;
    this.frame(data.center, data.boundingRadius);
  }

  /** Position the camera to frame a sphere of the given center and radius. */
  private frame(center: [number, number, number], radius: number): void {
    const target = new Vector3(...center);
    this.controls.target.copy(target);
    const dist = (radius + 2) / Math.tan((this.camera.fov * Math.PI) / 360);
    this.camera.position.set(target.x, target.y, target.z + dist * 1.3);
    this.camera.near = Math.max(0.1, dist * 0.01);
    this.camera.far = dist * 100;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  private animate = (): void => {
    requestAnimationFrame(this.animate);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  };

  private onResize = (): void => {
    const { clientWidth: w, clientHeight: h } = this.container;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  };
}

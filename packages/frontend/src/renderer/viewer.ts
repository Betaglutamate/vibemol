import {
  AmbientLight,
  BufferAttribute,
  BufferGeometry,
  Color,
  CylinderGeometry,
  DirectionalLight,
  Group,
  InstancedMesh,
  LineBasicMaterial,
  LineSegments,
  Material,
  Matrix4,
  Mesh,
  MeshStandardMaterial,
  Object3D,
  CanvasTexture,
  DoubleSide,
  LineDashedMaterial,
  MeshBasicMaterial,
  OrthographicCamera,
  PerspectiveCamera,
  Points,
  PointsMaterial,
  Quaternion,
  Raycaster,
  Scene,
  Sprite,
  SpriteMaterial,
  SphereGeometry,
  Texture,
  Uint32BufferAttribute,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { SSAOPass } from "three/addons/postprocessing/SSAOPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

import type { DecodedScene, DecodedGroup, Label } from "../protocol/types";

const UNIT_SPHERE = new SphereGeometry(1, 20, 14);
const UNIT_CYLINDER = new CylinderGeometry(1, 1, 1, 12, 1, true); // along +Y
const Y_AXIS = new Vector3(0, 1, 0);

// The Phase 1 renderer: draws a whole scene of objects, each made of draw groups
// (spheres / cylinders / lines / points). The camera is client-owned, so
// interaction never round-trips. GPU impostor shaders replace the instanced
// meshes in a later performance pass; the public surface stays the same.
export class Viewer {
  private readonly scene = new Scene();
  private camera: PerspectiveCamera | OrthographicCamera; // the active camera
  private readonly perspCamera: PerspectiveCamera;
  private readonly orthoCamera: OrthographicCamera;
  private orthographic = false;
  private viewHalfHeight = 10; // ortho frustum half-height (world units)
  private readonly renderer: WebGLRenderer;
  private readonly controls: OrbitControls;
  private readonly root = new Group();
  private readonly disposables: (BufferGeometry | Material | Texture)[] = [];
  private readonly pickMeshes: InstancedMesh[] = [];
  private readonly raycaster = new Raycaster();
  private pointerDown: { x: number; y: number } | null = null;
  private hasFramed = false;
  private lastCenter: [number, number, number] = [0, 0, 0];
  private lastRadius = 10;
  private composer: EffectComposer | null = null;
  private quality = false;

  /** Set by the app to receive click-to-pick events (with modifier keys). */
  onPick:
    | ((objectName: string, atomIndex: number, mods: { range: boolean; add: boolean }) => void)
    | null = null;

  constructor(private readonly container: HTMLElement) {
    this.scene.background = new Color(0x0b0d10);
    this.scene.add(this.root);

    const { clientWidth: w, clientHeight: h } = container;
    this.perspCamera = new PerspectiveCamera(45, w / h, 0.1, 5000);
    this.perspCamera.position.set(0, 0, 40);
    this.orthoCamera = new OrthographicCamera(-1, 1, 1, -1, 0.1, 5000);
    this.orthoCamera.position.set(0, 0, 40);
    this.camera = this.perspCamera;

    // preserveDrawingBuffer lets us snapshot the canvas to a PNG on demand.
    this.renderer = new WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setSize(w, h);
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;

    this.scene.add(new AmbientLight(0xffffff, 0.6));
    const key = new DirectionalLight(0xffffff, 0.85);
    key.position.set(1, 1, 1);
    this.scene.add(key);

    window.addEventListener("resize", this.onResize);
    const canvas = this.renderer.domElement;
    canvas.addEventListener("pointerdown", (e) => (this.pointerDown = { x: e.clientX, y: e.clientY }));
    canvas.addEventListener("pointerup", this.onPointerUp);
    this.animate();
  }

  /** Rebuild the rendered scene from a decoded scene message. */
  setScene(scene: DecodedScene): void {
    this.clear();
    if (scene.settings.bg_color) {
      this.scene.background = new Color(scene.settings.bg_color);
    }
    for (const obj of scene.objects) {
      if (!obj.visible) continue;
      for (const group of obj.groups) this.root.add(this.buildGroup(group));
      this.addPickMesh(obj.name, obj.pickPositions);
    }
    if (scene.measurementLines) this.root.add(this.dashedLines(scene.measurementLines));
    if (scene.selectionPoints) this.root.add(this.selectionMarkers(scene.selectionPoints));
    for (const label of scene.labels) this.root.add(this.label(label));

    this.lastCenter = scene.center;
    this.lastRadius = scene.boundingRadius;
    if (!this.hasFramed && scene.objects.length > 0) {
      this.frameTo(scene.center, scene.boundingRadius);
      this.hasFramed = true;
    }
    // Re-arm framing when the scene empties, so the next load re-zooms.
    if (scene.objects.length === 0) this.hasFramed = false;
  }

  /** Reframe the camera to show the whole molecule (client-side, instant). */
  resetView(): void {
    this.frameTo(this.lastCenter, this.lastRadius);
  }

  /** Render once and return a PNG data URL of the current view. */
  snapshot(): string {
    this.renderFrame();
    return this.renderer.domElement.toDataURL("image/png");
  }

  /** Toggle the high-quality screen-space ambient occlusion pass. */
  setQuality(on: boolean): boolean {
    this.quality = on;
    if (on && !this.composer) this.buildComposer();
    return this.quality;
  }

  private buildComposer(): void {
    const { clientWidth: w, clientHeight: h } = this.container;
    const composer = new EffectComposer(this.renderer);
    composer.addPass(new RenderPass(this.scene, this.camera));
    const ssao = new SSAOPass(this.scene, this.camera, w, h);
    ssao.kernelRadius = 8;
    ssao.minDistance = 0.002;
    ssao.maxDistance = 0.1;
    composer.addPass(ssao);
    composer.addPass(new OutputPass());
    this.composer = composer;
  }

  /** Move the camera to frame a sphere of the given center and radius. */
  frameTo(center: [number, number, number], radius: number): void {
    const target = new Vector3(...center);
    this.controls.target.copy(target);
    const dist = (radius + 3) / Math.tan((this.perspCamera.fov * Math.PI) / 360);
    const dir = new Vector3().subVectors(this.camera.position, target).normalize();
    if (dir.lengthSq() < 1e-6) dir.set(0, 0, 1);
    this.camera.position.copy(target).addScaledVector(dir, dist * 1.3);
    this.camera.near = Math.max(0.1, dist * 0.01);
    this.camera.far = dist * 100;
    this.viewHalfHeight = radius + 3;
    if (this.camera === this.orthoCamera) this.updateOrthoFrustum();
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  /** Switch between perspective and orthographic projection, preserving the view. */
  setProjection(orthographic: boolean): void {
    if (orthographic === this.orthographic) return;
    this.orthographic = orthographic;
    const to = orthographic ? this.orthoCamera : this.perspCamera;
    to.position.copy(this.camera.position);
    to.quaternion.copy(this.camera.quaternion);
    this.camera = to;
    this.controls.object = to;
    if (this.composer) {
      this.composer = null; // rebuilt against the new camera on next quality use
      if (this.quality) this.buildComposer();
    }
    this.frameTo(this.lastCenter, this.lastRadius);
  }

  /** Toggle continuous auto-rotation (OrbitControls handles it each frame). */
  setSpin(on: boolean): void {
    this.controls.autoRotate = on;
    this.controls.autoRotateSpeed = 2.0;
  }

  private updateOrthoFrustum(): void {
    const aspect = this.container.clientWidth / this.container.clientHeight;
    const h = this.viewHalfHeight;
    this.orthoCamera.left = -h * aspect;
    this.orthoCamera.right = h * aspect;
    this.orthoCamera.top = h;
    this.orthoCamera.bottom = -h;
    this.orthoCamera.updateProjectionMatrix();
  }

  private buildGroup(group: DecodedGroup): Object3D {
    switch (group.primitive) {
      case "spheres":
        return this.instancedSpheres(group.count, group.positions, group.radii, group.colors);
      case "cylinders":
        return this.instancedCylinders(group);
      case "lines":
        return this.lineSegments(group.positions, group.colors);
      case "points":
        return this.points(group.positions, group.colors, group.size);
      case "mesh":
        return this.mesh(group.positions, group.normals, group.colors, group.indices);
    }
  }

  private mesh(
    positions: Float32Array,
    normals: Float32Array,
    colors: Float32Array,
    indices: Uint32Array,
  ): Mesh {
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new BufferAttribute(positions, 3));
    geometry.setAttribute("normal", new BufferAttribute(normals, 3));
    geometry.setAttribute("color", new BufferAttribute(colors, 3));
    geometry.setIndex(new Uint32BufferAttribute(indices, 1));
    const material = new MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.5,
      metalness: 0.0,
      side: DoubleSide,
    });
    this.disposables.push(geometry, material);
    return new Mesh(geometry, material);
  }

  private instancedSpheres(
    count: number,
    positions: Float32Array,
    radii: Float32Array,
    colors: Float32Array,
  ): InstancedMesh {
    const material = new MeshStandardMaterial({ roughness: 0.45, metalness: 0.0 });
    const mesh = new InstancedMesh(UNIT_SPHERE, material, count);
    const dummy = new Object3D();
    const color = new Color();
    for (let i = 0; i < count; i++) {
      dummy.position.set(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]);
      dummy.scale.setScalar(radii[i]);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
      mesh.setColorAt(i, color.setRGB(colors[i * 3], colors[i * 3 + 1], colors[i * 3 + 2]));
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    this.disposables.push(material);
    return mesh;
  }

  private instancedCylinders(group: Extract<DecodedGroup, { primitive: "cylinders" }>): InstancedMesh {
    const { count, starts, ends, radii, colors } = group;
    const material = new MeshStandardMaterial({ roughness: 0.45, metalness: 0.0 });
    const mesh = new InstancedMesh(UNIT_CYLINDER, material, count);
    const color = new Color();
    const start = new Vector3();
    const end = new Vector3();
    const dir = new Vector3();
    const mid = new Vector3();
    const quat = new Quaternion();
    const scale = new Vector3();
    const matrix = new Matrix4();
    for (let i = 0; i < count; i++) {
      start.set(starts[i * 3], starts[i * 3 + 1], starts[i * 3 + 2]);
      end.set(ends[i * 3], ends[i * 3 + 1], ends[i * 3 + 2]);
      dir.subVectors(end, start);
      const len = dir.length() || 1e-4;
      mid.addVectors(start, end).multiplyScalar(0.5);
      quat.setFromUnitVectors(Y_AXIS, dir.normalize());
      scale.set(radii[i], len, radii[i]);
      matrix.compose(mid, quat, scale);
      mesh.setMatrixAt(i, matrix);
      mesh.setColorAt(i, color.setRGB(colors[i * 3], colors[i * 3 + 1], colors[i * 3 + 2]));
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    this.disposables.push(material);
    return mesh;
  }

  private lineSegments(positions: Float32Array, colors: Float32Array): LineSegments {
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new BufferAttribute(positions, 3));
    geometry.setAttribute("color", new BufferAttribute(colors, 3));
    const material = new LineBasicMaterial({ vertexColors: true });
    this.disposables.push(geometry, material);
    return new LineSegments(geometry, material);
  }

  private points(positions: Float32Array, colors: Float32Array, size: number): Points {
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new BufferAttribute(positions, 3));
    geometry.setAttribute("color", new BufferAttribute(colors, 3));
    const material = new PointsMaterial({ size, vertexColors: true, sizeAttenuation: false });
    this.disposables.push(geometry, material);
    return new Points(geometry, material);
  }

  /** Invisible per-atom spheres used only for click-to-pick raycasting. */
  private addPickMesh(objectName: string, positions: Float32Array): void {
    const count = positions.length / 3;
    if (count === 0) return;
    const material = new MeshBasicMaterial({ colorWrite: false, depthWrite: false });
    const mesh = new InstancedMesh(UNIT_SPHERE, material, count);
    mesh.userData.objectName = objectName;
    const dummy = new Object3D();
    for (let i = 0; i < count; i++) {
      dummy.position.set(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]);
      dummy.scale.setScalar(0.6);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
    this.disposables.push(material);
    this.pickMeshes.push(mesh);
    this.root.add(mesh);
  }

  private selectionMarkers(positions: Float32Array): Points {
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new BufferAttribute(positions, 3));
    const material = new PointsMaterial({
      color: 0xff3df0,
      size: 9,
      sizeAttenuation: false,
      depthTest: false,
    });
    this.disposables.push(geometry, material);
    return new Points(geometry, material);
  }

  private onPointerUp = (e: PointerEvent): void => {
    const down = this.pointerDown;
    this.pointerDown = null;
    if (!down || !this.onPick) return;
    if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) return; // a drag, not a click

    const rect = this.renderer.domElement.getBoundingClientRect();
    const pointer = new Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(pointer, this.camera);
    const hits = this.raycaster.intersectObjects(this.pickMeshes, false);
    if (hits.length && hits[0].instanceId != null) {
      const mods = { range: e.shiftKey, add: e.metaKey || e.ctrlKey };
      this.onPick(hits[0].object.userData.objectName as string, hits[0].instanceId, mods);
    }
  };

  private dashedLines(positions: Float32Array): LineSegments {
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new BufferAttribute(positions, 3));
    const line = new LineSegments(
      geometry,
      new LineDashedMaterial({ color: 0xffe24d, dashSize: 0.4, gapSize: 0.25 }),
    );
    line.computeLineDistances(); // required for dashes to show
    this.disposables.push(geometry, line.material as Material);
    return line;
  }

  private label(label: Label): Sprite {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 64;
    const ctx = canvas.getContext("2d")!;
    ctx.font = "32px ui-monospace, monospace";
    ctx.fillStyle = "#ffe24d";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label.text, 128, 32);
    const texture: Texture = new CanvasTexture(canvas);
    const material = new SpriteMaterial({ map: texture, depthTest: false, transparent: true });
    const sprite = new Sprite(material);
    sprite.position.set(...label.pos);
    sprite.scale.set(4, 1, 1);
    this.disposables.push(material, texture);
    return sprite;
  }

  private clear(): void {
    for (const child of [...this.root.children]) {
      this.root.remove(child);
      if (child instanceof Mesh && child.geometry !== UNIT_SPHERE && child.geometry !== UNIT_CYLINDER) {
        child.geometry.dispose();
      }
      if (child instanceof InstancedMesh) child.dispose();
    }
    this.pickMeshes.length = 0;
    for (const d of this.disposables) d.dispose();
    this.disposables.length = 0;
  }

  private animate = (): void => {
    requestAnimationFrame(this.animate);
    this.controls.update();
    this.renderFrame();
  };

  private renderFrame(): void {
    if (this.quality && this.composer) this.composer.render();
    else this.renderer.render(this.scene, this.camera);
  }

  private onResize = (): void => {
    const { clientWidth: w, clientHeight: h } = this.container;
    this.perspCamera.aspect = w / h;
    this.perspCamera.updateProjectionMatrix();
    this.updateOrthoFrustum();
    this.renderer.setSize(w, h);
    this.composer?.setSize(w, h);
  };
}

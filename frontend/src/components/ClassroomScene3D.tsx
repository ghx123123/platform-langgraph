import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { CSS2DObject, CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js';
import type { ClassroomEvent, LessonSlide } from '../types/workflow';
import './ClassroomScene3D.css';

type AgentId = 'teacher' | 'student:high' | 'student:medium' | 'student:low' | 'supervisor';

function normalizeSceneAgent(value?: string | null): AgentId | null {
  const id = String(value || '').toLowerCase();
  if (id.includes('supervisor')) return 'supervisor';
  if (id.includes('teacher')) return 'teacher';
  if (id.includes('high') || id.includes('studenta')) return 'student:high';
  if (id.includes('medium') || id.includes('studentb')) return 'student:medium';
  if (id.includes('low') || id.includes('basic') || id.includes('studentc')) return 'student:low';
  return null;
}

interface ClassroomScene3DProps {
  slide?: LessonSlide;
  events: ClassroomEvent[];
  activeAgentId?: string | null;
  eventType?: string | null;
  status?: string;
  selectedAgentId?: string;
  onSelectAgent?: (agentId: AgentId) => void;
}

const ROLE_COLORS: Record<AgentId, number> = {
  teacher: 0x2f7bea,
  'student:high': 0xd9783b,
  'student:medium': 0x4e85c7,
  'student:low': 0xc7973f,
  supervisor: 0x7655bd,
};

function material(color: number, roughness = 0.7) {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness: 0.03 });
}

function toon(color: number) {
  return new THREE.MeshToonMaterial({ color });
}

function box(size: [number, number, number], position: [number, number, number], mat: THREE.Material, parent: THREE.Object3D) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), mat);
  mesh.position.set(...position);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}

function createSideWindows(parent: THREE.Object3D, side: -1 | 1) {
  const wallX = side < 0 ? -8.83 : 8.83;
  const glassX = side < 0 ? -8.77 : 8.77;
  const frame = material(0xb7c4d1, 0.45);
  const glass = new THREE.MeshStandardMaterial({ color: 0xb8d6ef, transparent: true, opacity: 0.44, roughness: 0.14 });
  for (const z of [-3.7, -0.7, 2.3]) {
    box([0.08, 2.55, 2.45], [wallX, 4.15, z], frame, parent);
    box([0.035, 2.3, 2.18], [glassX, 4.15, z], glass, parent);
    box([0.05, 2.3, 0.06], [side < 0 ? -8.73 : 8.73, 4.15, z], frame, parent);
    box([0.05, 0.06, 2.18], [side < 0 ? -8.73 : 8.73, 4.15, z], frame, parent);
    box([0.28, 0.09, 2.5], [side < 0 ? -8.72 : 8.72, 2.9, z], material(0xd1dae3, 0.55), parent);
  }
}

function createDesk(parent: THREE.Object3D, x: number, z: number, accent: number) {
  const top = material(0xf8fafc, 0.55);
  const dark = material(0x34465d, 0.42);
  box([2.2, 0.13, 1.02], [x, 1.18, z], top, parent);
  for (const dx of [-0.82, 0.82]) box([0.07, 1.02, 0.07], [x + dx, 0.62, z], dark, parent);
  box([1.72, 0.07, 0.07], [x, 0.62, z + 0.41], dark, parent);
  const seat = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, 0.14, 24), material(0x2d4158, 0.54));
  seat.position.set(x, 0.72, z + 0.74); seat.castShadow = true; parent.add(seat);
  box([0.7, 0.68, 0.11], [x, 1.08, z + 1], material(accent, 0.62), parent);
  box([0.06, 0.55, 0.06], [x, 0.78, z + 0.9], dark, parent);
  box([0.38, 0.035, 0.28], [x + 0.38, 1.29, z - 0.12], material(0x1d2b3d, 0.25), parent);
}

function localMesh(geometry: THREE.BufferGeometry, meshMaterial: THREE.Material, position: [number, number, number], name = '') {
  const mesh = new THREE.Mesh(geometry, meshMaterial);
  mesh.position.set(...position); mesh.name = name; mesh.castShadow = true;
  return mesh;
}

function createArm(color: number, skinColor: number, name: string) {
  const arm = new THREE.Group(); arm.name = name;
  const upper = localMesh(new THREE.CapsuleGeometry(0.085, 0.31, 8, 14), toon(color), [0, -0.14, 0]);
  const lower = localMesh(new THREE.CapsuleGeometry(0.075, 0.23, 8, 14), toon(color), [0, -0.43, 0]);
  const hand = localMesh(new THREE.SphereGeometry(0.105, 14, 10), toon(skinColor), [0, -0.66, 0]);
  hand.scale.set(0.85, 1, 0.8); arm.add(upper, lower, hand); return arm;
}

function createHair(style: 'short' | 'bob' | 'long', color: number) {
  const hair = new THREE.Group();
  const cap = localMesh(new THREE.SphereGeometry(0.4, 20, 14, 0, Math.PI * 2, 0, Math.PI * 0.72), toon(color), [0, 0, 0]);
  cap.scale.set(1.04, 1.08, style === 'bob' ? 0.96 : 1.02); hair.add(cap);
  if (style === 'bob') hair.add(localMesh(new THREE.BoxGeometry(0.72, 0.38, 0.5), toon(color), [0, -0.2, -0.1]));
  if (style === 'long') for (const side of [-1, 1]) {
    const strand = localMesh(new THREE.CapsuleGeometry(0.08, 0.38, 7, 12), toon(color), [side * 0.34, -0.18, 0]);
    strand.rotation.z = side * 0.08; hair.add(strand);
  }
  if (style === 'short') for (let index = -2; index <= 2; index += 1) {
    const tuft = localMesh(new THREE.ConeGeometry(0.1, 0.22, 6), toon(color), [index * 0.1, 0.29, 0.26]);
    tuft.rotation.x = -0.65; hair.add(tuft);
  }
  return hair;
}

function createAgent(parent: THREE.Object3D, id: AgentId, position: [number, number, number], rotationY: number) {
  const group = new THREE.Group(); group.name = id; group.position.set(...position); group.rotation.y = rotationY;
  const seated = id !== 'teacher'; const skinColor = 0xf0bc9c; const clothColor = ROLE_COLORS[id]; const pantsColor = id === 'supervisor' ? 0x2e2941 : 0x27384d;
  const torso = localMesh(new THREE.CapsuleGeometry(0.34, 0.72, 8, 16), toon(clothColor), [0, seated ? 1.34 : 1.48, 0], 'torso');
  torso.scale.set(0.95, seated ? 0.82 : 1.08, 0.72); torso.rotation.x = seated ? -0.1 : 0; group.add(torso);
  group.add(localMesh(new THREE.BoxGeometry(0.54, 0.18, 0.4), toon(pantsColor), [0, seated ? 0.84 : 0.9, 0], 'hip'));
  const head = localMesh(new THREE.SphereGeometry(0.36, 22, 16), toon(skinColor), [0, seated ? 2.12 : 2.38, 0], 'head');
  head.scale.set(0.92, 1.04, 0.92); group.add(head);
  const hair = createHair(id === 'teacher' || id === 'student:medium' ? 'short' : id === 'student:low' ? 'long' : 'bob', id === 'supervisor' ? 0x352951 : 0x19243a);
  hair.position.set(0, seated ? 2.25 : 2.51, -0.02); group.add(hair);
  for (const eyeX of [-0.12, 0.12]) {
    group.add(localMesh(new THREE.SphereGeometry(0.045, 10, 8), toon(0x111b31), [eyeX, seated ? 2.12 : 2.38, 0.32]));
    const blush = localMesh(new THREE.SphereGeometry(0.045, 10, 8), toon(0xf0a0a0), [eyeX * 1.3, seated ? 2.02 : 2.28, 0.33]);
    blush.scale.set(1.2, 0.65, 0.3); group.add(blush);
  }
  group.add(localMesh(new THREE.BoxGeometry(0.12, 0.024, 0.018), toon(0x9a5b58), [0, seated ? 1.97 : 2.23, 0.345]));
  const leftArm = createArm(clothColor, skinColor, 'arm-left');
  const rightArm = createArm(clothColor, skinColor, 'arm-right');
  if (id === 'teacher') {
    leftArm.position.set(-0.36, 1.54, 0.04); leftArm.rotation.z = 0.35;
    rightArm.position.set(0.48, 1.82, 0.08); rightArm.rotation.set(0.15, 0, -1);
    const pointer = localMesh(new THREE.BoxGeometry(0.05, 0.05, 0.72), toon(0xf7de8f), [0.7, 1.5, 0.14]);
    pointer.rotation.set(0.1, 0, 0.25); group.add(pointer);
  } else {
    leftArm.position.set(-0.38, 1.42, 0.2); leftArm.rotation.set(-0.95, 0.06, 0.1);
    rightArm.position.set(0.38, 1.42, 0.2); rightArm.rotation.set(-1.02, -0.06, -0.1);
    if (id === 'student:medium') { rightArm.position.set(0.28, 1.65, 0.34); rightArm.rotation.set(-0.18, 0, -0.85); head.rotation.y = -0.18; }
    if (id === 'student:low') { rightArm.position.set(0.3, 2.02, 0.08); rightArm.rotation.set(0.08, 0, -2.74); head.rotation.y = 0.12; }
    if (id === 'supervisor') {
      leftArm.position.set(-0.28, 1.44, 0.28); leftArm.rotation.set(-0.78, 0.12, 0.48);
      rightArm.position.set(0.28, 1.44, 0.28); rightArm.rotation.set(-0.72, -0.12, -0.42);
      const clipboard = localMesh(new THREE.BoxGeometry(0.5, 0.62, 0.07), material(0x56657a, 0.45), [0.24, 1.47, 0.42]);
      clipboard.rotation.set(-0.28, 0, -0.08); group.add(clipboard);
      group.add(localMesh(new THREE.BoxGeometry(0.28, 0.08, 0.02), toon(0x2e3748), [0, 2.12, 0.355]));
    }
  }
  group.add(leftArm, rightArm);
  for (const side of [-1, 1]) {
    if (seated) {
      const thigh = localMesh(new THREE.CapsuleGeometry(0.1, 0.34, 7, 12), toon(pantsColor), [side * 0.18, 0.8, 0.25], side < 0 ? 'leg-left' : 'leg-right');
      thigh.rotation.x = -Math.PI / 2.3; group.add(thigh);
      group.add(localMesh(new THREE.CapsuleGeometry(0.09, 0.35, 7, 12), toon(pantsColor), [side * 0.18, 0.48, 0.53]));
      group.add(localMesh(new THREE.BoxGeometry(0.2, 0.11, 0.38), toon(0x1b2636), [side * 0.18, 0.16, 0.62]));
    } else {
      group.add(localMesh(new THREE.CapsuleGeometry(0.095, 0.52, 7, 12), toon(pantsColor), [side * 0.18, 0.48, 0], side < 0 ? 'leg-left' : 'leg-right'));
      group.add(localMesh(new THREE.BoxGeometry(0.2, 0.11, 0.38), toon(0x1b2636), [side * 0.18, 0.13, 0.12]));
    }
  }
  const halo = new THREE.Mesh(new THREE.RingGeometry(0.58, 0.67, 40), new THREE.MeshBasicMaterial({ color: 0xf0ad3c, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false }));
  halo.rotation.x = -Math.PI / 2; halo.position.y = 0.04; halo.name = 'activeHalo'; group.add(halo);
  group.userData.baseY = group.position.y; group.userData.seated = seated;
  parent.add(group); return group;
}

function safeEvent(events: ClassroomEvent[]) {
  const sorted = [...events].sort((a, b) => a.sequence - b.sequence);
  return sorted[sorted.length - 1];
}

const AGENT_LABELS: Record<AgentId, { short: string; name: string }> = {
  teacher: { short: '师', name: '教师' },
  'student:high': { short: '拓', name: '拓展型学生 A' },
  'student:medium': { short: '进', name: '进阶型学生 B' },
  'student:low': { short: '基', name: '基础型学生 C' },
  supervisor: { short: '督', name: '督导' },
};

function wrapCanvasText(context: CanvasRenderingContext2D, text: string, x: number, y: number, maxWidth: number, lineHeight: number, maxLines = 2) {
  let line = '';
  let lineIndex = 0;
  for (const character of text) {
    const next = line + character;
    if (context.measureText(next).width > maxWidth && line) {
      context.fillText(line, x, y + lineIndex * lineHeight);
      line = character; lineIndex += 1;
      if (lineIndex >= maxLines) return y + lineIndex * lineHeight;
    } else line = next;
  }
  if (line && lineIndex < maxLines) context.fillText(line, x, y + lineIndex * lineHeight);
  return y + (lineIndex + 1) * lineHeight;
}

function drawSlideTexture(texture: THREE.CanvasTexture, slide?: LessonSlide) {
  const canvas = texture.image as HTMLCanvasElement;
  const context = canvas.getContext('2d');
  if (!context) return;

  const ppt = slide?.ppt_content;
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = '#fbfcfd';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = '#2b6f9e';
  context.fillRect(0, 0, 18, canvas.height);

  context.fillStyle = '#2b6f9e';
  context.font = '700 24px "Microsoft YaHei", Arial';
  context.fillText(ppt?.subtitle || 'LESSON BLUEPRINT', 82, 74);

  context.fillStyle = '#17243a';
  context.font = '700 54px "Microsoft YaHei", Arial';
  const titleEnd = wrapCanvasText(
    context,
    ppt?.title || slide?.title || '正在载入本页课件',
    82,
    146,
    1050,
    64,
    2,
  );

  context.font = '28px "Microsoft YaHei", Arial';
  let bulletY = titleEnd + 52;
  const bullets = (ppt?.bullets || []).slice(0, 4);
  bullets.forEach((bullet) => {
    context.fillStyle = '#d58b28';
    context.fillRect(88, bulletY - 17, 11, 11);
    context.fillStyle = '#33455a';
    bulletY = wrapCanvasText(context, bullet, 122, bulletY, 720, 42, 2) + 10;
  });

  const example = (ppt?.examples || [])[0];
  const codeBlock = (ppt?.code_blocks || [])[0];
  if (example || codeBlock) {
    const panelX = 875;
    const panelY = Math.max(292, Math.min(470, titleEnd + 62));
    const panelWidth = 335;
    const panelHeight = 162;
    context.fillStyle = codeBlock ? '#14243b' : '#fff3d9';
    context.fillRect(panelX, panelY, panelWidth, panelHeight);
    context.fillStyle = '#d58b28';
    context.fillRect(panelX, panelY, 7, panelHeight);
    context.fillStyle = codeBlock ? '#d8e8f6' : '#5d4a2f';
    context.font = `${codeBlock ? '22px ui-monospace, Consolas' : '24px "Microsoft YaHei", Arial'}`;
    const panelText = codeBlock
      ? String(codeBlock.code || codeBlock.content || '')
      : String(example);
    wrapCanvasText(context, panelText, panelX + 28, panelY + 42, panelWidth - 48, 34, 3);
  }

  context.fillStyle = '#7d8b9c';
  context.font = '18px ui-monospace, Consolas';
  context.fillText(slide?.slide_id || 'draft', 82, canvas.height - 42);
  texture.needsUpdate = true;
}

export function ClassroomScene3D({ slide, events, activeAgentId, eventType, status, selectedAgentId = 'teacher', onSelectAgent }: ClassroomScene3DProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const screenTextureRef = useRef<THREE.CanvasTexture | null>(null);
  const slideRef = useRef(slide);
  const stateRef = useRef({ activeAgentId, eventType, selectedAgentId, onSelectAgent });
  const viewRef = useRef<{ reset: () => void; front: () => void; focus: (id: AgentId) => void } | null>(null);
  slideRef.current = slide;
  stateRef.current = { activeAgentId, eventType, selectedAgentId, onSelectAgent };

  useEffect(() => {
    const texture = screenTextureRef.current;
    if (!texture) return;
    drawSlideTexture(texture, slide);
  }, [slide]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xc7d7e6);
    scene.fog = new THREE.Fog(0xc7d7e6, 24, 46);
    const camera = new THREE.PerspectiveCamera(52, 1, 0.1, 100);
    // Director view: an elevated rear three-quarter angle keeps the board,
    // Teacher, all three students and the rear Supervisor in the same frame.
    // The previous low/close camera put the Supervisor in the foreground and
    // cropped every other character in the platform's wide scene pane.
    const homeCamera = new THREE.Vector3(7.2, 6.15, 9.4);
    const homeTarget = new THREE.Vector3(0, 1.9, -2.35);
    camera.position.copy(homeCamera);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(Math.max(window.devicePixelRatio || 1, 1.5), 2.25));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.02;
    renderer.domElement.setAttribute('role', 'img');
    renderer.domElement.setAttribute(
      'aria-label',
      '交互式三维课堂：教师在讲台授课，三名学生坐在前排，督导在后排旁听。可拖动调整视角并点击角色查看当前任务。',
    );
    host.appendChild(renderer.domElement);
    const labelRenderer = new CSS2DRenderer();
    labelRenderer.setSize(1, 1);
    labelRenderer.domElement.className = 'classroom-scene-label-layer';
    host.appendChild(labelRenderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(homeTarget);
    controls.enableDamping = true;
    controls.dampingFactor = 0.065;
    controls.minDistance = 1.2;
    controls.maxDistance = 25;
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.minPolarAngle = Math.PI * 0.12;
    controls.zoomToCursor = true;
    controls.screenSpacePanning = true;
    controls.rotateSpeed = 0.9;
    scene.add(new THREE.HemisphereLight(0xf8fbff, 0x607995, 2.1));
    const key = new THREE.DirectionalLight(0xfff6e7, 3.1);
    key.position.set(-7, 12, 8);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.left = -14; key.shadow.camera.right = 14;
    key.shadow.camera.top = 14; key.shadow.camera.bottom = -14;
    scene.add(key);
    const fill = new THREE.PointLight(0xb9dcff, 10, 18); fill.position.set(5, 4.8, 8); scene.add(fill);
    const warm = new THREE.PointLight(0xffd9ae, 8, 15); warm.position.set(-5, 3.6, -1); scene.add(warm);
    const root = new THREE.Group();
    scene.add(root);
    box([18, 0.24, 20], [0, -0.15, 0], material(0x94a8bb, 0.84), root);
    box([18, 8, 0.25], [0, 4, -7], material(0xe7edf3, 0.92), root);
    box([0.25, 8, 14], [-9, 4, 0], material(0xdfe8f0, 0.9), root);
    box([0.25, 8, 14], [9, 4, 0], material(0xe8eef4, 0.9), root);
    box([18, 0.18, 20], [0, 8.05, 0], material(0xf4f7fa, 0.95), root);
    for (let x = -8.5; x < 9; x += 1) box([0.015, 0.004, 20], [x, 0.001, 0], material(0x7d92a8, 0.9), root);
    for (let z = -9.5; z < 10; z += 1) box([18, 0.004, 0.015], [0, 0.001, z], material(0x7d92a8, 0.9), root);
    for (const lightX of [-6, -2, 2, 6]) for (const lightZ of [-3, 2]) {
      box([2.1, 0.08, 0.5], [lightX, 7.93, lightZ], material(0xcfd7df, 0.45), root);
      box([1.85, 0.035, 0.34], [lightX, 7.86, lightZ], new THREE.MeshBasicMaterial({ color: 0xffffff }), root);
    }
    createSideWindows(root, -1); createSideWindows(root, 1);
    box([8.75, 3.45, 0.28], [0.6, 4.95, -6.78], material(0x17243a, 0.5), root);
    box([8.25, 3.02, 0.08], [0.6, 4.95, -6.62], material(0x0d1829, 0.35), root);
    box([2.15, 2.65, 0.09], [-4.95, 4.95, -6.59], material(0xf7fafc, 0.7), root);
    box([1.45, 2.65, 0.09], [5.75, 4.95, -6.59], material(0xf7fafc, 0.7), root);
    const slideCanvas = document.createElement('canvas'); slideCanvas.width = 1280; slideCanvas.height = 720;
    const slideTexture = new THREE.CanvasTexture(slideCanvas); slideTexture.colorSpace = THREE.SRGBColorSpace; screenTextureRef.current = slideTexture;
    drawSlideTexture(slideTexture, slideRef.current);
    const slidePlane = new THREE.Mesh(new THREE.PlaneGeometry(7.95, 2.74), new THREE.MeshBasicMaterial({ map: slideTexture }));
    slidePlane.position.set(0.6, 4.95, -6.47); root.add(slidePlane);
    createDesk(root, -3, -2, 0xdfe8f2);
    createDesk(root, 0, -2, 0xdfe8f2);
    createDesk(root, 3, -2, 0xdfe8f2);
    createDesk(root, 0, 2.25, 0xd7ddec);
    box([2.15, 0.16, 0.88], [-0.7, 1.22, -5], material(0xf7f9fb, 0.55), root);
    box([1.65, 1, 0.62], [-0.7, 0.67, -5], material(0xcfd8e2, 0.65), root);
    box([1.5, 2.1, 0.48], [-7.75, 1.15, -4.55], material(0x8c684d, 0.7), root);
    for (const shelfY of [0.45, 0.95, 1.45]) box([1.36, 0.07, 0.42], [-7.75, shelfY, -4.55], material(0x684b38, 0.55), root);
    for (let index = 0; index < 14; index += 1) box(
      [0.08 + 0.03 * (index % 2), 0.38 + 0.06 * (index % 3), 0.25],
      [-8.28 + (index % 7) * 0.17, 0.65 + Math.floor(index / 7) * 0.55, -4.33],
      material([0x4a7cc8, 0xd56a62, 0x6aa876, 0xe1a54b][index % 4], 0.45), root,
    );
    const agents: Record<AgentId, THREE.Group> = {
      teacher: createAgent(root, 'teacher', [-0.9, 0, -5.38], 0.12),
      'student:high': createAgent(root, 'student:high', [-3, 0, -1.3], Math.PI),
      'student:medium': createAgent(root, 'student:medium', [0, 0, -1.3], Math.PI),
      'student:low': createAgent(root, 'student:low', [3, 0, -1.3], Math.PI),
      supervisor: createAgent(root, 'supervisor', [0, 0, 2.92], Math.PI),
    };
    const resetView = () => { camera.position.copy(homeCamera); controls.target.copy(homeTarget); controls.update(); };
    const frontView = () => { camera.position.set(0.35, 6.35, 12.6); controls.target.set(0, 1.85, -2.4); controls.update(); };
    const focusAgent = (id: AgentId) => {
      const agent = agents[id];
      if (!agent) return;
      const target = agent.position.clone().add(new THREE.Vector3(0, 1.42, 0));
      // Students face the board (-Z), so a front-side close-up is placed
      // towards the board; Teacher close-up stays on the audience side.
      const offset = id === 'teacher'
        ? new THREE.Vector3(3.6, 2.3, 4.8)
        : id === 'supervisor'
          ? new THREE.Vector3(4.2, 2.45, 4.8)
          : new THREE.Vector3(4.6, 2.25, -3.8);
      camera.position.copy(target).add(offset);
      controls.target.copy(target);
      controls.update();
    };
    viewRef.current = { reset: resetView, front: frontView, focus: focusAgent };

    Object.entries(agents).forEach(([id, agent]) => {
      const label = document.createElement('button');
      label.type = 'button';
      label.className = `scene-agent-label ${id.replace(':', '-')}`;
      label.textContent = AGENT_LABELS[id as AgentId].name;
      label.title = `查看${AGENT_LABELS[id as AgentId].name}当前任务`;
      label.addEventListener('click', event => {
        event.stopPropagation();
        const agentId = id as AgentId;
        stateRef.current.onSelectAgent?.(agentId);
        viewRef.current?.focus(agentId);
      });
      const object = new CSS2DObject(label);
      object.position.set(
        id === 'student:medium' ? -0.18 : id === 'supervisor' ? 0.22 : 0,
        id === 'teacher' ? 2.9 : id === 'supervisor' ? 2.68 : 2.54,
        0,
      );
      agent.add(object);
    });

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let pointerDown: [number, number] | null = null;
    const selectAt = (clientX: number, clientY: number) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      pointer.set(((clientX - bounds.left) / bounds.width) * 2 - 1, -((clientY - bounds.top) / bounds.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(Object.values(agents), true)[0]?.object;
      let candidate: THREE.Object3D | null | undefined = hit;
      while (candidate && !Object.prototype.hasOwnProperty.call(agents, candidate.name)) candidate = candidate.parent;
      const id = normalizeSceneAgent(candidate?.name);
      if (id) {
        stateRef.current.onSelectAgent?.(id);
        viewRef.current?.focus(id);
      }
    };
    const pointerDownHandler = (event: PointerEvent) => { pointerDown = [event.clientX, event.clientY]; };
    const pointerUpHandler = (event: PointerEvent) => {
      if (!pointerDown) return;
      const distance = Math.hypot(event.clientX - pointerDown[0], event.clientY - pointerDown[1]);
      pointerDown = null;
      if (distance <= 8) selectAt(event.clientX, event.clientY);
    };
    renderer.domElement.addEventListener('pointerdown', pointerDownHandler);
    renderer.domElement.addEventListener('pointerup', pointerUpHandler);
    const clock = new THREE.Clock();
    let frame = 0;
    const render = () => {
      frame = window.requestAnimationFrame(render);
      const t = clock.getElapsedTime();
      Object.entries(agents).forEach(([id, agent]) => {
        const active = normalizeSceneAgent(stateRef.current.activeAgentId) === id;
        const halo = agent.getObjectByName('activeHalo') as THREE.Mesh | undefined;
        if (halo?.material instanceof THREE.MeshBasicMaterial) halo.material.opacity = active || stateRef.current.selectedAgentId === id ? (active ? 0.78 : 0.35) : 0;
        const head = agent.getObjectByName('head');
        if (head) head.rotation.z = Math.sin(t * 0.7 + id.length) * 0.012;
        if (!agent.userData.seated) agent.position.y = agent.userData.baseY + Math.sin(t * 1.7 + id.length) * 0.012;
        const rightArm = agent.getObjectByName('arm-right');
        const leftArm = agent.getObjectByName('arm-left');
        if (rightArm) rightArm.rotation.z = (id === 'teacher' && active ? -.65 + Math.sin(t * 2.4) * .12 : .15);
        if (leftArm) leftArm.rotation.z = id !== 'teacher' && active ? .72 + Math.sin(t * 2.1) * .08 : -.15;
      });
      controls.update();
      renderer.render(scene, camera);
      labelRenderer.render(scene, camera);
    };
    const resize = () => {
      const width = Math.max(host.clientWidth, 320);
      const height = Math.max(host.clientHeight, 360);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      labelRenderer.setSize(width, height);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
    render();
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener('pointerdown', pointerDownHandler);
      renderer.domElement.removeEventListener('pointerup', pointerUpHandler);
      renderer.dispose();
      labelRenderer.domElement.remove();
      viewRef.current = null;
      root.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        object.geometry.dispose();
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        materials.forEach((item) => item.dispose());
      });
      screenTextureRef.current?.dispose();
      screenTextureRef.current = null;
      host.removeChild(renderer.domElement);
    };
  }, []);

  const latest = safeEvent(events);
  const title = slide?.ppt_content?.title || slide?.title || '等待 Lesson Blueprint';
  return <section className="classroom-scene-card" aria-label="3D classroom simulation">
    <div ref={hostRef} className="classroom-scene-canvas" />
    <div className="classroom-scene-overlay">
      <div><span className="scene-kicker">LIVE CLASSROOM</span><strong>{title}</strong><small>{latest ? `EVT-${String(latest.sequence).padStart(3, '0')} · ${latest.event_type}` : '等待服务端 ClassroomEvent'}</small></div>
      <span className={`scene-status ${status || 'idle'}`}>{status === 'active' ? '演练中' : status === 'paused' ? '已暂停' : status === 'completed' ? '本轮完成' : '等待事件'}</span>
    </div>
    <div className="scene-view-controls"><button type="button" onClick={() => viewRef.current?.reset()}>重置视角</button><button type="button" onClick={() => viewRef.current?.front()}>前视角</button></div>
  </section>;
}

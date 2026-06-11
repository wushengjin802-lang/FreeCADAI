"use client";

import { Alert, Spin } from "antd";
import { useEffect, useRef, useState } from "react";

type Vec3 = [number, number, number];
type Triangle = [Vec3, Vec3, Vec3];

function parseBinaryStl(buffer: ArrayBuffer): Triangle[] {
  const view = new DataView(buffer);
  const count = view.getUint32(80, true);
  const triangles: Triangle[] = [];
  let offset = 84;
  for (let i = 0; i < count && offset + 50 <= buffer.byteLength; i += 1) {
    offset += 12;
    const tri: Vec3[] = [];
    for (let v = 0; v < 3; v += 1) {
      tri.push([view.getFloat32(offset, true), view.getFloat32(offset + 4, true), view.getFloat32(offset + 8, true)]);
      offset += 12;
    }
    triangles.push(tri as Triangle);
    offset += 2;
  }
  return triangles;
}

function parseAsciiStl(text: string): Triangle[] {
  const vertices = [...text.matchAll(/vertex\s+(-?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s+(-?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s+(-?\d+(?:\.\d+)?(?:e[-+]?\d+)?)/gi)]
    .map((match) => [Number(match[1]), Number(match[2]), Number(match[3])] as Vec3);
  const triangles: Triangle[] = [];
  for (let i = 0; i + 2 < vertices.length; i += 3) {
    triangles.push([vertices[i], vertices[i + 1], vertices[i + 2]]);
  }
  return triangles;
}

async function parseStl(blob: Blob): Promise<Triangle[]> {
  const buffer = await blob.arrayBuffer();
  if (buffer.byteLength >= 84) {
    const count = new DataView(buffer).getUint32(80, true);
    if (84 + count * 50 === buffer.byteLength) return parseBinaryStl(buffer);
  }
  return parseAsciiStl(new TextDecoder().decode(buffer));
}

function bounds(triangles: Triangle[]) {
  const points = triangles.flat();
  const min: Vec3 = [Infinity, Infinity, Infinity];
  const max: Vec3 = [-Infinity, -Infinity, -Infinity];
  points.forEach((point) => {
    for (let i = 0; i < 3; i += 1) {
      min[i] = Math.min(min[i], point[i]);
      max[i] = Math.max(max[i], point[i]);
    }
  });
  const center: Vec3 = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2];
  const span = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 1);
  return { center, span };
}

function project(point: Vec3, center: Vec3, span: number, angle: number, width: number, height: number): [number, number] {
  const x0 = (point[0] - center[0]) / span;
  const y0 = (point[1] - center[1]) / span;
  const z0 = (point[2] - center[2]) / span;
  const ca = Math.cos(angle);
  const sa = Math.sin(angle);
  const cb = Math.cos(angle * 0.55);
  const sb = Math.sin(angle * 0.55);
  const x1 = x0 * ca - z0 * sa;
  const z1 = x0 * sa + z0 * ca;
  const y1 = y0 * cb - z1 * sb;
  const z2 = y0 * sb + z1 * cb;
  const scale = Math.min(width, height) * 0.78;
  const perspective = 1.4 / (1.8 + z2);
  return [width / 2 + x1 * scale * perspective, height / 2 - y1 * scale * perspective];
}

export function StlPreviewer({ blob, height = 420 }: { blob: Blob | null; height?: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [triangles, setTriangles] = useState<Triangle[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let canceled = false;
    setTriangles([]);
    setError("");
    if (!blob) return;
    parseStl(blob)
      .then((rows) => {
        if (!canceled) {
          if (!rows.length) setError("未能解析 STL 顶点数据。");
          setTriangles(rows.slice(0, 6000));
        }
      })
      .catch((err) => !canceled && setError(err instanceof Error ? err.message : "STL 解析失败"));
    return () => {
      canceled = true;
    };
  }, [blob]);

  useEffect(() => {
    if (!triangles.length) return;
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    const { center, span } = bounds(triangles);
    let frame = 0;
    let raf = 0;
    const draw = () => {
      const width = canvas.clientWidth;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(width * dpr));
      canvas.height = Math.max(1, Math.floor(height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);
      context.fillStyle = "#f7faf6";
      context.fillRect(0, 0, width, height);
      context.strokeStyle = "#315142";
      context.lineWidth = 0.7;
      const angle = frame * 0.012;
      context.beginPath();
      triangles.forEach((tri) => {
        const a = project(tri[0], center, span, angle, width, height);
        const b = project(tri[1], center, span, angle, width, height);
        const c = project(tri[2], center, span, angle, width, height);
        context.moveTo(a[0], a[1]);
        context.lineTo(b[0], b[1]);
        context.lineTo(c[0], c[1]);
        context.lineTo(a[0], a[1]);
      });
      context.stroke();
      frame += 1;
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [height, triangles]);

  if (error) return <Alert type="warning" showIcon message={error} />;
  if (!triangles.length) return <Spin />;
  return <canvas ref={canvasRef} className="stl-preview-canvas" style={{ height }} />;
}

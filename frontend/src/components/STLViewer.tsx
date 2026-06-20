import * as React from "react"
import * as THREE from "three"
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js"
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js"
import { X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"

// Lightweight STL viewer ported from the Jinja order_detail. The URL is served
// by Flask (same-origin via the Vite proxy in dev), so the session cookie is
// sent automatically. 3MF files are converted to STL server-side.
export function STLViewer({
  url,
  title,
  onClose,
}: {
  url: string
  title: string
  onClose: () => void
}) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    let disposed = false

    const w = canvas.clientWidth || 600
    const h = canvas.clientHeight || 380
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
    renderer.setSize(w, h, false)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x1a1a2e)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(45, w / h, 0.01, 50000)

    scene.add(new THREE.AmbientLight(0xffffff, 0.5))
    const dir = new THREE.DirectionalLight(0xffffff, 0.9)
    dir.position.set(1, 2, 3)
    scene.add(dir)
    const dir2 = new THREE.DirectionalLight(0xaaaaff, 0.3)
    dir2.position.set(-2, -1, -1)
    scene.add(dir2)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08

    let raf = 0
    const animate = () => {
      if (disposed) return
      raf = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    const onResize = () => {
      const w2 = canvas.clientWidth
      const h2 = canvas.clientHeight
      if (w2 === 0 || h2 === 0) return
      camera.aspect = w2 / h2
      camera.updateProjectionMatrix()
      renderer.setSize(w2, h2, false)
    }
    window.addEventListener("resize", onResize)

    let mesh: THREE.Mesh | null = null
    let grid: THREE.GridHelper | null = null
    const loader = new STLLoader()
    loader.load(
      url,
      (geo) => {
        if (disposed) return
        geo.computeBoundingBox()
        const center = new THREE.Vector3()
        geo.boundingBox!.getCenter(center)
        geo.translate(-center.x, -center.y, -center.z)
        const mat = new THREE.MeshPhongMaterial({
          color: 0x2196f3,
          specular: 0x444444,
          shininess: 50,
        })
        mesh = new THREE.Mesh(geo, mat)
        // 3MF/Bambu uses Z-up; rotate so models stand upright in Three.js (Y-up).
        mesh.rotation.x = -Math.PI / 2
        scene.add(mesh)

        const box = new THREE.Box3().setFromObject(mesh)
        const size = new THREE.Vector3()
        box.getSize(size)
        const maxDim = Math.max(size.x, size.y, size.z) || 1
        camera.position.set(0, maxDim * 0.4, maxDim * 2.0)
        camera.near = maxDim * 0.001
        camera.far = maxDim * 40
        camera.updateProjectionMatrix()
        controls.target.set(0, 0, 0)
        controls.update()

        grid = new THREE.GridHelper(maxDim * 10, 40, 0x4444aa, 0x222244)
        grid.position.y = box.min.y
        grid.material.transparent = true
        grid.material.opacity = 0.55
        scene.add(grid)

        setLoading(false)
        onResize()
      },
      undefined,
      () => {
        if (!disposed) {
          setError("Could not load the 3D model.")
          setLoading(false)
        }
      }
    )

    return () => {
      disposed = true
      cancelAnimationFrame(raf)
      window.removeEventListener("resize", onResize)
      controls.dispose()
      if (mesh) {
        scene.remove(mesh)
        mesh.geometry.dispose()
        ;(mesh.material as THREE.Material).dispose()
      }
      if (grid) {
        scene.remove(grid)
        grid.geometry.dispose()
        ;(grid.material as THREE.Material).dispose()
      }
      renderer.dispose()
    }
  }, [url])

  return (
    <div className="overflow-hidden rounded-xl border border-border shadow-sm">
      <div className="flex items-center justify-between border-b border-border bg-card px-4 py-2.5">
        <span className="text-sm font-medium">{title}</span>
        <Button size="sm" variant="ghost" onClick={onClose}>
          <X className="size-4" /> Close
        </Button>
      </div>
      <div className="relative" style={{ background: "#1a1a2e" }}>
        <canvas
          ref={canvasRef}
          className="block h-[380px] w-full"
          style={{ display: "block" }}
        />
        {loading && !error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <Spinner className="size-6 text-white/70" />
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-white/80">
            {error}
          </div>
        )}
      </div>
    </div>
  )
}

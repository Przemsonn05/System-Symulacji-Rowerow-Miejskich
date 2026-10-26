// Kamera orbitalna: PPM - obrot, LPM / SPM - przesuwanie, kolko - zoom, WASD/QE, tryb kinowy (C).
using UnityEngine;
using UnityEngine.EventSystems;

namespace Veturilo.Viz
{
    public class CameraRig : MonoBehaviour
    {
        public Vector3 target = Vector3.zero;
        public float yaw = 20f, pitch = 55f, distance = 9000f;
        public float minDistance = 150f, maxDistance = 30000f;
        public bool cinematic;
        public bool InputEnabled = true;

        Vector3 tTarget; float tYaw, tPitch, tDistance;
        Vector2 lastMouse;
        bool dragging; int dragButton = -1;
        Camera cam;

        public bool MouseOverUi => EventSystem.current != null && EventSystem.current.IsPointerOverGameObject();
        /// Czy ostatnie wcisniecie LPM bylo przeciaganiem (wtedy nie traktujemy go jako klikniecia).
        public bool WasDrag { get; private set; }
        Vector2 pressPos;

        void Awake()
        {
            cam = GetComponent<Camera>();
            tTarget = target; tYaw = yaw; tPitch = pitch; tDistance = distance;
        }

        public void Preset(Vector3 tgt, float y, float p, float d, bool instant = false)
        {
            tTarget = tgt; tYaw = y; tPitch = p; tDistance = d;
            cinematic = false;
            if (instant) { target = tgt; yaw = y; pitch = p; distance = d; Apply(); }
        }

        void LateUpdate()
        {
            float dt = Time.unscaledDeltaTime;
            if (InputEnabled) HandleInput(dt);
            if (cinematic)
            {
                tYaw += dt * 4f;
                tPitch = 38f + 8f * Mathf.Sin(Time.unscaledTime * 0.05f);
                tDistance = 6500f + 2500f * Mathf.Sin(Time.unscaledTime * 0.035f);
                tTarget = Vector3.Lerp(tTarget, Vector3.zero, dt * 0.2f);
            }
            float k = 1f - Mathf.Exp(-dt * 8f);
            target = Vector3.Lerp(target, tTarget, k);
            yaw = Mathf.LerpAngle(yaw, tYaw, k);
            pitch = Mathf.Lerp(pitch, tPitch, k);
            distance = Mathf.Lerp(distance, tDistance, k);
            Apply();
        }

        void Apply()
        {
            var rot = Quaternion.Euler(pitch, yaw, 0);
            transform.position = target - rot * Vector3.forward * distance;
            transform.rotation = rot;
            if (cam) cam.farClipPlane = Mathf.Max(60000f, distance * 6f);
        }

        void HandleInput(float dt)
        {
            Vector2 m = InputCompat.MousePosition;
            Vector2 delta = m - lastMouse;
            lastMouse = m;

            for (int b = 0; b < 3; b++)
            {
                if (InputCompat.MouseDown(b) && !MouseOverUi)
                {
                    dragging = true; dragButton = b; pressPos = m;
                    if (b == 0) WasDrag = false;
                }
            }
            if (dragging && !InputCompat.MouseHeld(dragButton)) { dragging = false; dragButton = -1; }

            if (dragging)
            {
                if (dragButton == 0 && (m - pressPos).sqrMagnitude > 36f) WasDrag = true;
                if (dragButton == 1 || (dragButton == 0 && InputCompat.Held(K.Shift)))
                {
                    tYaw += delta.x * 0.25f;
                    tPitch = Mathf.Clamp(tPitch - delta.y * 0.2f, 12f, 89f);
                    cinematic = false;
                }
                else if (WasDrag || dragButton == 2)
                {
                    Pan(-delta * (tDistance / Mathf.Max(Screen.height, 1)) * 1.1f);
                }
            }

            float scroll = MouseOverUi ? 0f : InputCompat.Scroll;
            if (Mathf.Abs(scroll) > 0.01f)
            {
                tDistance = Mathf.Clamp(tDistance * Mathf.Pow(0.88f, scroll), minDistance, maxDistance);
                cinematic = false;
            }

            Vector2 move = Vector2.zero;
            if (InputCompat.Held(K.W)) move.y += 1;
            if (InputCompat.Held(K.S)) move.y -= 1;
            if (InputCompat.Held(K.D)) move.x += 1;
            if (InputCompat.Held(K.A)) move.x -= 1;
            if (move != Vector2.zero) Pan(move * tDistance * 0.8f * dt);
            if (InputCompat.Held(K.Q)) { tYaw -= 60f * dt; cinematic = false; }
            if (InputCompat.Held(K.E)) { tYaw += 60f * dt; cinematic = false; }
        }

        void Pan(Vector2 screenDelta)
        {
            var right = Quaternion.Euler(0, tYaw, 0) * Vector3.right;
            var fwd = Quaternion.Euler(0, tYaw, 0) * Vector3.forward;
            tTarget += right * screenDelta.x + fwd * screenDelta.y;
            tTarget.x = Mathf.Clamp(tTarget.x, -20000, 20000);
            tTarget.z = Mathf.Clamp(tTarget.z, -20000, 20000);
            cinematic = false;
        }

        public void FocusOn(Vector3 p, float d = 2200f)
        {
            tTarget = new Vector3(p.x, 0, p.z);
            tDistance = d;
            tPitch = Mathf.Clamp(tPitch, 35f, 60f);
            cinematic = false;
        }
    }
}

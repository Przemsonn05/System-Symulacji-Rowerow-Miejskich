// Jedno API wejscia dla starego Input Managera i nowego Input System (domyslny w Unity 6).
using UnityEngine;
#if !ENABLE_LEGACY_INPUT_MANAGER && ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace Veturilo.Viz
{
    public enum K { Space, Left, Right, Up, Down, W, A, S, D, Q, E, C, H, R, F1, Digit1, Digit2, Digit3, Digit4, LeftBracket, RightBracket, Comma, Period, Escape, Shift }

    public static class InputCompat
    {
#if !ENABLE_LEGACY_INPUT_MANAGER && ENABLE_INPUT_SYSTEM
        static Key Map(K k)
        {
            switch (k)
            {
                case K.Space: return Key.Space;
                case K.Left: return Key.LeftArrow;
                case K.Right: return Key.RightArrow;
                case K.Up: return Key.UpArrow;
                case K.Down: return Key.DownArrow;
                case K.W: return Key.W;
                case K.A: return Key.A;
                case K.S: return Key.S;
                case K.D: return Key.D;
                case K.Q: return Key.Q;
                case K.E: return Key.E;
                case K.C: return Key.C;
                case K.H: return Key.H;
                case K.R: return Key.R;
                case K.F1: return Key.F1;
                case K.Digit1: return Key.Digit1;
                case K.Digit2: return Key.Digit2;
                case K.Digit3: return Key.Digit3;
                case K.Digit4: return Key.Digit4;
                case K.LeftBracket: return Key.LeftBracket;
                case K.RightBracket: return Key.RightBracket;
                case K.Comma: return Key.Comma;
                case K.Period: return Key.Period;
                case K.Escape: return Key.Escape;
                default: return Key.LeftShift;
            }
        }

        public static bool Down(K k) => Keyboard.current != null && Keyboard.current[Map(k)].wasPressedThisFrame;
        public static bool Held(K k)
        {
            if (Keyboard.current == null) return false;
            if (k == K.Shift) return Keyboard.current.leftShiftKey.isPressed || Keyboard.current.rightShiftKey.isPressed;
            return Keyboard.current[Map(k)].isPressed;
        }
        public static Vector2 MousePosition => Mouse.current != null ? Mouse.current.position.ReadValue() : Vector2.zero;
        // Od Input System 1.6.3 jeden "zabek" kolka to +-1; starsze wersje (i czesc platform)
        // podaja surowe +-120 z Windows. Normalizujemy oba przypadki do +-1 na zabek.
        public static float Scroll
        {
            get
            {
                if (Mouse.current == null) return 0f;
                float y = Mouse.current.scroll.ReadValue().y;
                return Mathf.Abs(y) > 10f ? y / 120f : y;
            }
        }
        public static bool MouseHeld(int b) => Mouse.current != null && Btn(b).isPressed;
        public static bool MouseDown(int b) => Mouse.current != null && Btn(b).wasPressedThisFrame;
        public static bool MouseUp(int b) => Mouse.current != null && Btn(b).wasReleasedThisFrame;
        static UnityEngine.InputSystem.Controls.ButtonControl Btn(int b) =>
            b == 0 ? Mouse.current.leftButton : b == 1 ? Mouse.current.rightButton : Mouse.current.middleButton;
#else
        static KeyCode Map(K k)
        {
            switch (k)
            {
                case K.Space: return KeyCode.Space;
                case K.Left: return KeyCode.LeftArrow;
                case K.Right: return KeyCode.RightArrow;
                case K.Up: return KeyCode.UpArrow;
                case K.Down: return KeyCode.DownArrow;
                case K.W: return KeyCode.W;
                case K.A: return KeyCode.A;
                case K.S: return KeyCode.S;
                case K.D: return KeyCode.D;
                case K.Q: return KeyCode.Q;
                case K.E: return KeyCode.E;
                case K.C: return KeyCode.C;
                case K.H: return KeyCode.H;
                case K.R: return KeyCode.R;
                case K.F1: return KeyCode.F1;
                case K.Digit1: return KeyCode.Alpha1;
                case K.Digit2: return KeyCode.Alpha2;
                case K.Digit3: return KeyCode.Alpha3;
                case K.Digit4: return KeyCode.Alpha4;
                case K.LeftBracket: return KeyCode.LeftBracket;
                case K.RightBracket: return KeyCode.RightBracket;
                case K.Comma: return KeyCode.Comma;
                case K.Period: return KeyCode.Period;
                case K.Escape: return KeyCode.Escape;
                default: return KeyCode.LeftShift;
            }
        }

        public static bool Down(K k) => Input.GetKeyDown(Map(k));
        public static bool Held(K k) => k == K.Shift
            ? Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift)
            : Input.GetKey(Map(k));
        public static Vector2 MousePosition => Input.mousePosition;
        public static float Scroll => Input.mouseScrollDelta.y;
        public static bool MouseHeld(int b) => Input.GetMouseButton(b);
        public static bool MouseDown(int b) => Input.GetMouseButtonDown(b);
        public static bool MouseUp(int b) => Input.GetMouseButtonUp(b);
#endif
    }
}

// Slady calego dnia: kazdy odcinek trasy przejazdu to czworokat rozszerzany w shaderze w bok
// (normal = kierunek poszerzenia, uv.y = strona -1/+1), o szerokosci rosnacej z odlegloscia kamery
// (mniej wiecej staly rozmiar na ekranie). uv.x = chwila przejazdu tego punktu [s od polnocy] -
// punkt jest widoczny dopiero, gdy _TimeCut >= uv.x, wiec slad rosnie razem z rowerem.
// Mieszanie addytywne: tam, gdzie jedzie wiele rowerow, slad jasnieje (korytarze rowerowe miasta).
Shader "Veturilo/DayTrails"
{
    Properties
    {
        _Color ("Color", Color) = (1, 1, 1, 0.08)
        _TimeCut ("Time cut", Float) = 0
        _Width ("Width", Float) = 1
    }
    SubShader
    {
        Tags { "Queue" = "Transparent+30" "RenderType" = "Transparent" "IgnoreProjector" = "True" }
        Blend SrcAlpha One
        ZWrite Off
        Cull Off
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            float4 _Color;
            float _TimeCut;
            float _Width;

            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; float2 uv : TEXCOORD0; float4 color : COLOR; };
            struct v2f { float4 pos : SV_POSITION; float4 col : COLOR; float edge : TEXCOORD0; };

            v2f vert (appdata v)
            {
                v2f o;
                float3 w = mul(unity_ObjectToWorld, v.vertex).xyz;
                float d = distance(_WorldSpaceCameraPos, w);
                float width = _Width * max(d * 0.0011, 1.2);
                w += v.normal * v.uv.y * width;
                o.pos = mul(UNITY_MATRIX_VP, float4(w, 1));
                o.col = v.color * _Color;
                o.col.a *= step(v.uv.x, _TimeCut);
                o.edge = v.uv.y;
                return o;
            }

            fixed4 frag (v2f i) : SV_Target
            {
                float a = 1 - abs(i.edge);
                return float4(i.col.rgb, i.col.a * a);
            }
            ENDCG
        }
    }
}

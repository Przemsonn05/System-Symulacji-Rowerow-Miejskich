// Woda (Wisla, jeziora) w URP: fale z sumy sinusoid (bez tekstur), odbicie lustrzane miasta i nieba
// (_ReflectionTex z PlanarReflection.cs; bez niego kolor nieba), wspolczynnik Fresnela, odblask slonca, mgla.
Shader "Veturilo/Water"
{
    Properties
    {
        _BaseColor ("Deep color", Color) = (0.05, 0.12, 0.18, 1)
        _SkyColor ("Sky color (no reflection)", Color) = (0.5, 0.6, 0.7, 1)
        _ReflectionTex ("Reflection", 2D) = "black" {}
        _HasReflection ("Has reflection", Float) = 0
        _ReflStrength ("Reflection strength", Float) = 1
        _WaveStrength ("Wave strength", Float) = 0.35
        _Distortion ("Reflection distortion", Float) = 0.025
    }
    SubShader
    {
        Tags { "RenderType" = "Opaque" "RenderPipeline" = "UniversalPipeline" "Queue" = "Geometry+10" }
        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _BaseColor;
                half4 _SkyColor;
                float _HasReflection;
                float _ReflStrength;
                float _WaveStrength;
                float _Distortion;
            CBUFFER_END
            TEXTURE2D(_ReflectionTex);
            SAMPLER(sampler_ReflectionTex);

            struct Attributes { float4 positionOS : POSITION; };
            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float4 screenPos : TEXCOORD1;
                float fog : TEXCOORD2;
            };

            Varyings vert (Attributes i)
            {
                Varyings o;
                VertexPositionInputs p = GetVertexPositionInputs(i.positionOS.xyz);
                o.positionCS = p.positionCS;
                o.positionWS = p.positionWS;
                o.screenPos = ComputeScreenPos(p.positionCS);
                o.fog = ComputeFogFactor(p.positionCS.z);
                return o;
            }

            // nachylenie powierzchni = suma pochodnych kilku fal o roznych kierunkach i dlugosciach
            float2 WaveSlope(float2 xz, float t)
            {
                float2 g = 0;
                float2 d;
                d = float2(0.80, 0.60);  g += d * cos(dot(xz, d) * 0.045 + t * 0.9);
                d = float2(-0.50, 0.86); g += d * cos(dot(xz, d) * 0.071 + t * 1.3) * 0.7;
                d = float2(0.30, -0.95); g += d * cos(dot(xz, d) * 0.13 + t * 1.9) * 0.45;
                d = float2(-0.92, -0.38); g += d * cos(dot(xz, d) * 0.27 + t * 2.6) * 0.3;
                d = float2(0.62, -0.78); g += d * cos(dot(xz, d) * 0.55 + t * 3.4) * 0.18;
                return g;
            }

            half4 frag (Varyings i) : SV_Target
            {
                float2 g = WaveSlope(i.positionWS.xz, _Time.y) * _WaveStrength;
                float3 n = normalize(float3(-g.x, 1, -g.y));
                float3 v = normalize(GetCameraPositionWS() - i.positionWS);
                float fresnel = 0.06 + 0.94 * pow(1 - saturate(dot(n, v)), 5);

                float2 uv = i.screenPos.xy / i.screenPos.w + n.xz * _Distortion;
                half3 refl = _HasReflection > 0.5
                    ? SAMPLE_TEXTURE2D(_ReflectionTex, sampler_ReflectionTex, uv).rgb
                    : _SkyColor.rgb;

                Light sun = GetMainLight();
                float lit = saturate(sun.direction.y) * 0.8 + 0.2;
                half3 deep = _BaseColor.rgb * (sun.color * lit + SampleSH(float3(0, 1, 0)));
                float3 h = normalize(sun.direction + v);
                half3 spec = sun.color * pow(saturate(dot(n, h)), 600) * 6 * saturate(sun.direction.y * 4);

                half3 col = lerp(deep, refl * _ReflStrength, saturate(fresnel * 1.35 + 0.18)) + spec;
                col = MixFog(col, i.fog);
                return half4(col, 1);
            }
            ENDHLSL
        }
    }
}

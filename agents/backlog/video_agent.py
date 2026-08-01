"""
video_agent.py
-----------------
Agente responsável por gerar vídeos curtos a partir de um roteiro/tema.

Este agente segue uma arquitetura em duas camadas:

1. Roteirização (sempre feita via LLM): transforma um tema em um roteiro
   estruturado de cenas (texto na tela, narração, duração).
2. Renderização do vídeo: por padrão usa um renderizador local de "slideshow"
   (texto + imagem de fundo + narração via TTS, com moviepy), que funciona
   sem depender de serviços pagos de geração de vídeo por IA.

Se o projeto tiver acesso a uma API de geração de vídeo por IA (ex: Runway,
Pika, Luma, Sora API etc.), basta implementar uma função compatível com
`external_render_function` e passá-la no construtor — o agente usará essa
função no lugar do renderizador local.
"""

import os
from typing import Optional, Callable, Dict, Any, List

from .base_agent import BaseAgent


class VideoAgent(BaseAgent):
    """Agente de geração de vídeos curtos: roteiro (LLM) + renderização."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        external_render_function: Optional[Callable[[Dict[str, Any], str], str]] = None,
        **kwargs,
    ):
        """
        Args:
            external_render_function: função opcional
                `def renderizar(roteiro: dict, output_path: str) -> str`
                que integra com um serviço externo de geração de vídeo por IA.
                Se None, usa o renderizador local de slideshow (`render_slideshow`).
        """
        system_prompt = (
            "Você é um roteirista de vídeos curtos para redes sociais "
            "(estilo Reels/TikTok/Shorts). Transforme o tema recebido em um "
            "roteiro de cenas, com gancho forte nos primeiros segundos.\n\n"
            "Responda APENAS com um JSON válido no formato:\n"
            "{\n"
            '  "titulo": "<título do vídeo>",\n'
            '  "duracao_estimada_segundos": <número>,\n'
            '  "cenas": [\n'
            '     {"texto_tela": "<texto curto exibido na tela>", '
            '"narracao": "<texto a ser narrado em voz>", '
            '"duracao_segundos": <número>}\n'
            "  ]\n"
            "}\n"
            "Gere entre 4 e 8 cenas curtas, cada uma com no máximo 2 frases de narração."
        )
        super().__init__(
            name="VideoAgent",
            system_prompt=system_prompt,
            model=model,
            **kwargs,
        )
        self.external_render_function = external_render_function

    def generate_script(self, topic: str, target_duration_seconds: int = 30) -> Dict[str, Any]:
        """Gera o roteiro estruturado do vídeo a partir de um tema."""
        prompt = f"Tema do vídeo: {topic}\nDuração alvo total: ~{target_duration_seconds} segundos."
        resposta = self._call_llm(prompt)
        try:
            return self._extract_json(resposta)
        except ValueError:
            return {
                "titulo": topic,
                "duracao_estimada_segundos": target_duration_seconds,
                "cenas": [{"texto_tela": topic, "narracao": topic, "duracao_segundos": target_duration_seconds}],
            }

    def render_slideshow(
        self,
        script: Dict[str, Any],
        output_path: str = "video.mp4",
        size: tuple = (1080, 1920),
        background_color: tuple = (17, 24, 39),
        use_tts: bool = True,
    ) -> str:
        """
        Renderiza localmente um vídeo simples de "slideshow": cada cena vira
        um frame com o texto centralizado, com narração opcional via TTS
        (gTTS, sem custo de API), concatenados em um único MP4.

        Requer: moviepy, pillow e (opcionalmente) gTTS instalados.
        """
        from PIL import Image, ImageDraw, ImageFont
        from moviepy.editor import (
            ImageClip,
            concatenate_videoclips,
            AudioFileClip,
            CompositeAudioClip,
        )
        import tempfile

        clips = []
        temp_files = []

        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 64)
        except IOError:
            font = ImageFont.load_default()

        for i, cena in enumerate(script.get("cenas", [])):
            duracao = cena.get("duracao_segundos", 4)

            # Cria o frame (imagem) da cena
            img = Image.new("RGB", size, color=background_color)
            draw = ImageDraw.Draw(img)
            texto = cena.get("texto_tela", "")
            bbox = draw.multiline_textbbox((0, 0), texto, font=font, align="center")
            largura_texto = bbox[2] - bbox[0]
            altura_texto = bbox[3] - bbox[1]
            posicao = ((size[0] - largura_texto) / 2, (size[1] - altura_texto) / 2)
            draw.multiline_text(posicao, texto, font=font, fill=(255, 255, 255), align="center")

            frame_path = tempfile.mktemp(suffix=f"_cena{i}.png")
            img.save(frame_path)
            temp_files.append(frame_path)

            audio_clip = None
            if use_tts and cena.get("narracao"):
                try:
                    from gtts import gTTS

                    audio_path = tempfile.mktemp(suffix=f"_cena{i}.mp3")
                    gTTS(text=cena["narracao"], lang="pt").save(audio_path)
                    temp_files.append(audio_path)
                    audio_clip = AudioFileClip(audio_path)
                    duracao = max(duracao, audio_clip.duration)
                except Exception:
                    audio_clip = None  # segue sem narração se o TTS falhar

            clip = ImageClip(frame_path).set_duration(duracao)
            if audio_clip:
                clip = clip.set_audio(audio_clip)
            clips.append(clip)

        video_final = concatenate_videoclips(clips, method="compose")
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        video_final.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac", logger=None)

        for f in temp_files:
            try:
                os.remove(f)
            except OSError:
                pass

        return output_path

    def run(
        self,
        topic: str,
        output_path: str = "video.mp4",
        target_duration_seconds: int = 30,
        **render_kwargs,
    ) -> str:
        """Pipeline completo: gera o roteiro e renderiza o vídeo final."""
        roteiro = self.generate_script(topic, target_duration_seconds=target_duration_seconds)

        if self.external_render_function:
            return self.external_render_function(roteiro, output_path)

        return self.render_slideshow(roteiro, output_path=output_path, **render_kwargs)


if __name__ == "__main__":
    agent = VideoAgent()
    roteiro = agent.generate_script("3 dicas rápidas de produtividade para times remotos")
    print(roteiro)
    # Descomente para renderizar de fato (requer moviepy/gTTS instalados):
    # agent.run("3 dicas rápidas de produtividade para times remotos", output_path="outputs/video.mp4")

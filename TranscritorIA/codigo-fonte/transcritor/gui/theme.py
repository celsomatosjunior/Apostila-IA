"""Identidade visual: instrumento clínico silencioso.

Fundo cinza-azulado frio, tinta grafite, um único azul de coloração histológica
como acento, verde para concluído e vermelho para erro. Tipografia nativa do
Windows 11 (Segoe UI Variable), sem fontes embutidas — o executável fica menor.
"""

PAPER = "#EEF1F4"      # fundo da janela
SURFACE = "#FFFFFF"    # lista e painéis
INK = "#18212C"        # texto principal
MUTED = "#5E6A78"      # texto secundário
LINE = "#D5DCE4"       # divisórias
STAIN = "#24508F"      # acento (azul de metileno)
STAIN_SOFT = "#DCE6F4"
DONE = "#2E7A57"
ERROR = "#B3261E"
SPEECH = "#C3CCD7"     # fala ainda não transcrita na faixa da aula

FONT = '"Segoe UI Variable Text", "Segoe UI", "Noto Sans", sans-serif'

QSS = f"""
QWidget {{ font-family: {FONT}; font-size: 10pt; color: {INK}; }}
QMainWindow, #root {{ background: {PAPER}; }}
#title {{ font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif; font-size: 17pt; font-weight: 600; }}
#subtitle {{ color: {MUTED}; }}
#hwKey {{ color: {MUTED}; }}
#hwVal {{ font-weight: 600; }}
#hwPanel {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px; }}
#lessons {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px; }}
#dropHint {{ color: {MUTED}; font-size: 11pt; }}
#dropHintStrong {{ font-size: 13pt; font-weight: 600; }}
#lessonName {{ font-weight: 600; }}
#lessonMeta {{ color: {MUTED}; }}
#kindAudio, #kindVideo {{ border-radius: 4px; padding: 1px 0; font-size: 8.5pt; font-weight: 600; }}
#kindAudio {{ background: #E7ECF1; color: {MUTED}; }}
#kindVideo {{ background: {STAIN_SOFT}; color: {STAIN}; }}
#statusLine {{ color: {MUTED}; }}
#metric {{ font-size: 12pt; font-weight: 600; }}
#metricKey {{ color: {MUTED}; }}
#notice {{ background: {STAIN_SOFT}; border-radius: 6px; padding: 6px 10px; }}
QPushButton {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 6px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {STAIN}; }}
QPushButton:focus {{ border: 2px solid {STAIN}; }}
QPushButton:disabled {{ color: #9AA4AF; background: #F4F6F8; }}
QPushButton#primary {{ background: {STAIN}; color: white; border: none; font-weight: 600; padding: 9px 20px; }}
QPushButton#primary:hover {{ background: #1C4178; }}
QPushButton#primary:disabled {{ background: #9FB2CC; }}
QPushButton#danger {{ color: {ERROR}; }}
QProgressBar {{ background: #E3E8EE; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {STAIN}; border-radius: 4px; }}
QComboBox {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 6px; padding: 5px 8px; }}
QScrollArea {{ border: none; background: transparent; }}
QToolTip {{ background: {INK}; color: white; border: none; padding: 4px; }}
"""

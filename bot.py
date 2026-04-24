import discord
from discord.ext import commands
from discord import app_commands
import json
import asyncio
import datetime
import os

# ============================================================
#  CONFIGURACAO
# ============================================================
TOKEN = "MTQ5NzE3NjIyODk3NTYxMjAyNA.Go0UoF.S7IMHeehPOwJ1qUQdf9PkPP2rXaOHB8uhHq_ws"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================================
#  FICHEIROS JSON
# ============================================================
CONFIG_FILE = "ticket_config.json"
TICKETS_FILE = "tickets.json"

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_config():
    return load_json(CONFIG_FILE, {
        "categorias": [
            {"nome": "Suporte", "emoji": "🛠️", "descricao": "Precisa de ajuda?"},
            {"nome": "Duvidas", "emoji": "❓", "descricao": "Tem alguma duvida?"},
            {"nome": "Parceria", "emoji": "🤝", "descricao": "Quer ser parceiro?"},
        ],
        "cor": "#5865F2",
        "titulo": "Sistema de Tickets",
        "descricao": "Clica no botao abaixo para abrir um ticket!",
        "categoria_canal": None,
        "log_canal": None,
        "auto_close_horas": 24,
        "mensagem_abertura": "Ola {user}! O staff vai atender-te em breve.",
    })

def get_tickets():
    return load_json(TICKETS_FILE, {})

# ============================================================
#  ONLINE
# ============================================================
@bot.event
async def on_ready():
    print(f"Bot online como {bot.user}")
    synced = await bot.tree.sync()
    print(f"{len(synced)} comandos sincronizados.")
    await bot.change_presence(activity=discord.CustomActivity(name="Gerindo tickets e embeds 🎫"))
    bot.loop.create_task(auto_close_loop())

# ============================================================
#  TRACKING ULTIMA MSG (auto-close)
# ============================================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    tickets = get_tickets()
    for tid, tdata in tickets.items():
        if tdata.get("canal_id") == str(message.channel.id) and tdata.get("status") == "aberto":
            tdata["ultimo_msg"] = datetime.datetime.utcnow().isoformat()
            save_json(TICKETS_FILE, tickets)
            break
    await bot.process_commands(message)

# ============================================================
#  AUTO-CLOSE
# ============================================================
async def auto_close_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        config = get_config()
        horas = config.get("auto_close_horas", 24)
        tickets = get_tickets()
        agora = datetime.datetime.utcnow()
        for tid, tdata in list(tickets.items()):
            if tdata.get("status") != "aberto":
                continue
            ultimo = datetime.datetime.fromisoformat(tdata.get("ultimo_msg", agora.isoformat()))
            if (agora - ultimo).total_seconds() / 3600 >= horas:
                for guild in bot.guilds:
                    canal = guild.get_channel(int(tdata.get("canal_id", 0)))
                    if canal:
                        await canal.send("Ticket fechado automaticamente por inatividade.")
                        await asyncio.sleep(3)
                        await canal.delete()
                tickets[tid]["status"] = "fechado_auto"
        save_json(TICKETS_FILE, tickets)
        await asyncio.sleep(3600)

# ============================================================
#  TRANSCRIPT HTML
# ============================================================
def gerar_transcript_html(messages, ticket_id, user, category):
    msgs_html = ""
    for m in messages:
        if m.author.bot:
            continue
        ts = m.created_at.strftime("%d/%m/%Y %H:%M")
        msgs_html += f"""
        <div class="msg">
            <img class="avatar" src="{m.author.display_avatar.url}" />
            <div class="content">
                <span class="author">{m.author.display_name}</span>
                <span class="time">{ts}</span>
                <div class="text">{m.content}</div>
            </div>
        </div>"""
    return f"""<!DOCTYPE html><html lang="pt"><head><meta charset="UTF-8">
<title>Transcript #{ticket_id}</title>
<style>
body{{background:#313338;color:#dbdee1;font-family:'Segoe UI',sans-serif;padding:20px}}
h1{{color:#5865f2}}.info{{background:#2b2d31;border-radius:8px;padding:12px;margin-bottom:20px}}
.msg{{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #3f4147}}
.avatar{{width:40px;height:40px;border-radius:50%}}.author{{font-weight:bold;color:#fff;margin-right:8px}}
.time{{font-size:11px;color:#949ba4}}.text{{margin-top:4px;line-height:1.4}}
</style></head><body>
<h1>Transcript #{ticket_id}</h1>
<div class="info"><b>Utilizador:</b> {user}<br><b>Categoria:</b> {category}<br>
<b>Gerado em:</b> {datetime.datetime.now().strftime("%d/%m/%Y %H:%M")}</div>
{msgs_html}</body></html>"""

# ============================================================
#  AVALIACAO
# ============================================================
class AvaliacaoView(discord.ui.View):
    def __init__(self, ticket_id):
        super().__init__(timeout=300)
        for i in range(1, 6):
            btn = discord.ui.Button(label="⭐" * i, style=discord.ButtonStyle.secondary, row=0)
            btn.callback = self.make_cb(i, ticket_id)
            self.add_item(btn)

    def make_cb(self, estrelas, ticket_id):
        async def cb(interaction: discord.Interaction):
            tickets = get_tickets()
            if ticket_id in tickets:
                tickets[ticket_id]["avaliacao"] = estrelas
                save_json(TICKETS_FILE, tickets)
            embed = discord.Embed(title="Obrigado!", description=f"Deste **{'⭐'*estrelas}** ao atendimento.", color=0xFEE75C)
            await interaction.response.edit_message(embed=embed, view=None)
        return cb

# ============================================================
#  CONTROLO DO TICKET
# ============================================================
class TicketControlView(discord.ui.View):
    def __init__(self, ticket_id, owner_id):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.owner_id = owner_id

    @discord.ui.button(label="Fechar", emoji="🔒", style=discord.ButtonStyle.danger, row=0)
    async def fechar(self, interaction, button):
        if not interaction.user.guild_permissions.administrator and interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Sem permissao!", ephemeral=True)
        tickets = get_tickets()
        ticket = tickets.get(self.ticket_id, {})
        messages = [m async for m in interaction.channel.history(limit=500, oldest_first=True)]
        html = gerar_transcript_html(messages, self.ticket_id, ticket.get("owner_name","?"), ticket.get("categoria","?"))
        fname = f"transcript_{self.ticket_id}.html"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(html)
        config = get_config()
        if config.get("log_canal"):
            log_ch = interaction.guild.get_channel(int(config["log_canal"]))
            if log_ch:
                embed_log = discord.Embed(title=f"Ticket #{self.ticket_id} Fechado",
                    description=f"**Utilizador:** <@{ticket.get('owner_id')}>\n**Categoria:** {ticket.get('categoria')}\n**Fechado por:** {interaction.user.mention}",
                    color=0xED4245, timestamp=datetime.datetime.utcnow())
                await log_ch.send(embed=embed_log, file=discord.File(fname))
        try:
            owner = await interaction.guild.fetch_member(int(ticket.get("owner_id", 0)))
            if owner:
                embed_av = discord.Embed(title="Como foi o atendimento?", description="Avalia o suporte!", color=0xFEE75C)
                await owner.send(embed=embed_av, view=AvaliacaoView(self.ticket_id))
        except:
            pass
        if os.path.exists(fname):
            os.remove(fname)
        if self.ticket_id in tickets:
            tickets[self.ticket_id]["status"] = "fechado"
            save_json(TICKETS_FILE, tickets)
        await interaction.response.send_message("A fechar em 5 segundos...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="Claim", emoji="✋", style=discord.ButtonStyle.primary, row=0)
    async def claim(self, interaction, button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Apenas admins!", ephemeral=True)
        tickets = get_tickets()
        if self.ticket_id in tickets:
            tickets[self.ticket_id]["staff_id"] = str(interaction.user.id)
            save_json(TICKETS_FILE, tickets)
        button.label = f"Claim: {interaction.user.display_name}"
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"{interaction.user.mention} assumiu este ticket!")

    @discord.ui.button(label="Transcript", emoji="📄", style=discord.ButtonStyle.secondary, row=0)
    async def transcript(self, interaction, button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Sem permissao!", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        tickets = get_tickets()
        ticket = tickets.get(self.ticket_id, {})
        messages = [m async for m in interaction.channel.history(limit=500, oldest_first=True)]
        html = gerar_transcript_html(messages, self.ticket_id, ticket.get("owner_name","?"), ticket.get("categoria","?"))
        fname = f"transcript_{self.ticket_id}.html"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(html)
        await interaction.followup.send(file=discord.File(fname), ephemeral=True)
        os.remove(fname)

# ============================================================
#  CATEGORIAS VIEW
# ============================================================
class CategoriasView(discord.ui.View):
    def __init__(self, categorias):
        super().__init__(timeout=None)
        for cat in categorias:
            btn = discord.ui.Button(label=cat["nome"], emoji=cat.get("emoji","🎫"), style=discord.ButtonStyle.secondary)
            btn.callback = self.make_cb(cat)
            self.add_item(btn)

    def make_cb(self, cat):
        async def cb(interaction):
            await criar_ticket(interaction, cat)
        return cb

# ============================================================
#  CRIAR TICKET
# ============================================================
async def criar_ticket(interaction, categoria):
    await interaction.response.defer(ephemeral=True)
    config = get_config()
    tickets = get_tickets()
    guild = interaction.guild
    user = interaction.user
    for tid, tdata in tickets.items():
        if tdata.get("owner_id") == str(user.id) and tdata.get("status") == "aberto":
            ch = guild.get_channel(int(tdata.get("canal_id", 0)))
            if ch:
                return await interaction.followup.send(f"Ja tens ticket aberto: {ch.mention}", ephemeral=True)
    ticket_id = str(len(tickets) + 1).zfill(4)
    cat_id = config.get("categoria_canal")
    category_obj = guild.get_channel(int(cat_id)) if cat_id else None
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    for member in guild.members:
        if member.guild_permissions.administrator:
            overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    canal = await guild.create_text_channel(
        name=f"ticket-{ticket_id}-{user.name}", category=category_obj,
        overwrites=overwrites, topic=f"Ticket de {user.display_name} | {categoria['nome']}"
    )
    tickets[ticket_id] = {
        "owner_id": str(user.id), "owner_name": user.display_name,
        "canal_id": str(canal.id), "categoria": categoria["nome"],
        "status": "aberto", "staff_id": None, "avaliacao": None,
        "aberto_em": datetime.datetime.utcnow().isoformat(),
        "ultimo_msg": datetime.datetime.utcnow().isoformat(),
    }
    save_json(TICKETS_FILE, tickets)
    try:
        cor_int = int(config["cor"].lstrip("#"), 16)
    except:
        cor_int = 0x5865F2
    embed = discord.Embed(
        title=f"{categoria.get('emoji','')} Ticket #{ticket_id} — {categoria['nome']}",
        description=config["mensagem_abertura"].replace("{user}", user.mention),
        color=cor_int, timestamp=datetime.datetime.utcnow()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    await canal.send(content=user.mention, embed=embed, view=TicketControlView(ticket_id, user.id))
    if config.get("log_canal"):
        log_ch = guild.get_channel(int(config["log_canal"]))
        if log_ch:
            await log_ch.send(embed=discord.Embed(
                title=f"Ticket #{ticket_id} Aberto",
                description=f"**Utilizador:** {user.mention}\n**Categoria:** {categoria['nome']}",
                color=0x57F287, timestamp=datetime.datetime.utcnow()
            ))
    await interaction.followup.send(f"Ticket criado: {canal.mention}", ephemeral=True)

# ============================================================
#  CONFIG TICKETS (modals)
# ============================================================
class ModalConfigGeral(discord.ui.Modal, title="Configurar Painel"):
    titulo = discord.ui.TextInput(label="Titulo", max_length=256)
    descricao = discord.ui.TextInput(label="Descricao", style=discord.TextStyle.paragraph, max_length=1000)
    cor = discord.ui.TextInput(label="Cor hex (ex: #5865F2)", max_length=7)
    msg_abertura = discord.ui.TextInput(label="Mensagem de abertura (usa {user})", max_length=500)

    async def on_submit(self, interaction):
        config = get_config()
        config.update({"titulo": str(self.titulo), "descricao": str(self.descricao),
                        "cor": str(self.cor), "mensagem_abertura": str(self.msg_abertura)})
        save_json(CONFIG_FILE, config)
        await interaction.response.edit_message(embed=build_config_embed(), view=ConfigView())

class ModalConfigCanais(discord.ui.Modal, title="Canais e Auto-close"):
    log_canal = discord.ui.TextInput(label="ID do canal de logs", max_length=20)
    categoria_canal = discord.ui.TextInput(label="ID da categoria para tickets", max_length=20, required=False)
    auto_close = discord.ui.TextInput(label="Auto-close (horas)", max_length=3, placeholder="24")

    async def on_submit(self, interaction):
        config = get_config()
        config["log_canal"] = str(self.log_canal).strip()
        if str(self.categoria_canal).strip():
            config["categoria_canal"] = str(self.categoria_canal).strip()
        try:
            config["auto_close_horas"] = int(str(self.auto_close))
        except:
            pass
        save_json(CONFIG_FILE, config)
        await interaction.response.edit_message(embed=build_config_embed(), view=ConfigView())

class ModalAdicionarCategoria(discord.ui.Modal, title="Adicionar Categoria"):
    nome = discord.ui.TextInput(label="Nome", max_length=50)
    emoji = discord.ui.TextInput(label="Emoji", max_length=5, placeholder="🎫")
    descricao = discord.ui.TextInput(label="Descricao", max_length=100)

    async def on_submit(self, interaction):
        config = get_config()
        config["categorias"].append({"nome": str(self.nome), "emoji": str(self.emoji), "descricao": str(self.descricao)})
        save_json(CONFIG_FILE, config)
        await interaction.response.edit_message(embed=build_config_embed(), view=ConfigView())

def build_config_embed():
    config = get_config()
    try:
        cor_int = int(config["cor"].lstrip("#"), 16)
    except:
        cor_int = 0x5865F2
    embed = discord.Embed(title="Config — Sistema de Tickets", color=cor_int)
    embed.add_field(name="Titulo", value=config["titulo"], inline=False)
    embed.add_field(name="Cor", value=config["cor"], inline=True)
    embed.add_field(name="Auto-close", value=f"{config['auto_close_horas']}h", inline=True)
    embed.add_field(name="Logs", value=f"<#{config['log_canal']}>" if config.get("log_canal") else "Nao definido", inline=True)
    cats = "\n".join([f"{c.get('emoji','')} **{c['nome']}**" for c in config["categorias"]])
    embed.add_field(name="Categorias", value=cats or "Nenhuma", inline=False)
    return embed

class ConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Geral", emoji="⚙️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_geral(self, interaction, button):
        await interaction.response.send_modal(ModalConfigGeral())

    @discord.ui.button(label="Canais", emoji="📡", style=discord.ButtonStyle.secondary, row=0)
    async def btn_canais(self, interaction, button):
        await interaction.response.send_modal(ModalConfigCanais())

    @discord.ui.button(label="Adicionar Categoria", emoji="➕", style=discord.ButtonStyle.primary, row=1)
    async def btn_add(self, interaction, button):
        await interaction.response.send_modal(ModalAdicionarCategoria())

    @discord.ui.button(label="Limpar Categorias", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def btn_clear(self, interaction, button):
        config = get_config()
        config["categorias"] = []
        save_json(CONFIG_FILE, config)
        await interaction.response.edit_message(embed=build_config_embed(), view=ConfigView())

    @discord.ui.button(label="Publicar Painel", emoji="🚀", style=discord.ButtonStyle.success, row=2)
    async def btn_publicar(self, interaction, button):
        config = get_config()
        try:
            cor_int = int(config["cor"].lstrip("#"), 16)
        except:
            cor_int = 0x5865F2
        embed = discord.Embed(title=config["titulo"], description=config["descricao"], color=cor_int)
        await interaction.channel.send(embed=embed, view=CategoriasView(config["categorias"]))
        await interaction.response.send_message("Painel publicado!", ephemeral=True)

# ============================================================
#  SISTEMA DE EMBEDS
# ============================================================
embed_states = {}

def get_embed_state(user_id):
    if user_id not in embed_states:
        embed_states[user_id] = {"titulo": "Titulo do Embed", "descricao": "Descricao aqui...",
            "cor": "#5865F2", "autor": None, "rodape": None, "imagem": None, "thumbnail": None, "campos": []}
    return embed_states[user_id]

def build_embed_preview(state):
    try:
        cor_int = int(state["cor"].lstrip("#"), 16)
    except:
        cor_int = 0x5865F2
    embed = discord.Embed(title=state["titulo"], description=state["descricao"], color=cor_int)
    if state["autor"]: embed.set_author(name=state["autor"])
    if state["thumbnail"]: embed.set_thumbnail(url=state["thumbnail"])
    if state["imagem"]: embed.set_image(url=state["imagem"])
    if state["rodape"]: embed.set_footer(text=state["rodape"])
    for c in state["campos"]:
        embed.add_field(name=c["nome"], value=c["valor"], inline=True)
    return embed

class ModalETitulo(discord.ui.Modal, title="Titulo"):
    titulo = discord.ui.TextInput(label="Titulo", max_length=256)
    async def on_submit(self, interaction):
        get_embed_state(interaction.user.id)["titulo"] = str(self.titulo)
        await interaction.response.edit_message(embed=build_embed_preview(get_embed_state(interaction.user.id)), view=EmbedPainelView(interaction.user.id))

class ModalEDescricao(discord.ui.Modal, title="Descricao"):
    descricao = discord.ui.TextInput(label="Descricao", style=discord.TextStyle.paragraph, max_length=4000)
    async def on_submit(self, interaction):
        get_embed_state(interaction.user.id)["descricao"] = str(self.descricao)
        await interaction.response.edit_message(embed=build_embed_preview(get_embed_state(interaction.user.id)), view=EmbedPainelView(interaction.user.id))

class ModalECor(discord.ui.Modal, title="Cor"):
    cor = discord.ui.TextInput(label="Cor hex (ex: #ff0000)", max_length=7)
    async def on_submit(self, interaction):
        get_embed_state(interaction.user.id)["cor"] = str(self.cor)
        await interaction.response.edit_message(embed=build_embed_preview(get_embed_state(interaction.user.id)), view=EmbedPainelView(interaction.user.id))

class ModalEAutor(discord.ui.Modal, title="Autor"):
    autor = discord.ui.TextInput(label="Nome do autor", max_length=256)
    async def on_submit(self, interaction):
        get_embed_state(interaction.user.id)["autor"] = str(self.autor)
        await interaction.response.edit_message(embed=build_embed_preview(get_embed_state(interaction.user.id)), view=EmbedPainelView(interaction.user.id))

class ModalERodape(discord.ui.Modal, title="Rodape"):
    rodape = discord.ui.TextInput(label="Texto do rodape", max_length=2048)
    async def on_submit(self, interaction):
        get_embed_state(interaction.user.id)["rodape"] = str(self.rodape)
        await interaction.response.edit_message(embed=build_embed_preview(get_embed_state(interaction.user.id)), view=EmbedPainelView(interaction.user.id))

class ModalEImagem(discord.ui.Modal, title="Imagem e Thumbnail"):
    imagem = discord.ui.TextInput(label="URL imagem grande", required=False)
    thumbnail = discord.ui.TextInput(label="URL thumbnail (canto)", required=False)
    async def on_submit(self, interaction):
        state = get_embed_state(interaction.user.id)
        if str(self.imagem): state["imagem"] = str(self.imagem)
        if str(self.thumbnail): state["thumbnail"] = str(self.thumbnail)
        await interaction.response.edit_message(embed=build_embed_preview(state), view=EmbedPainelView(interaction.user.id))

class ModalECampo(discord.ui.Modal, title="Adicionar Campo"):
    nome = discord.ui.TextInput(label="Nome do campo", max_length=256)
    valor = discord.ui.TextInput(label="Valor do campo", style=discord.TextStyle.paragraph, max_length=1024)
    async def on_submit(self, interaction):
        state = get_embed_state(interaction.user.id)
        if len(state["campos"]) < 25:
            state["campos"].append({"nome": str(self.nome), "valor": str(self.valor)})
        await interaction.response.edit_message(embed=build_embed_preview(state), view=EmbedPainelView(interaction.user.id))

class ModalEImportarJSON(discord.ui.Modal, title="Importar JSON"):
    json_data = discord.ui.TextInput(label="Cole o JSON aqui", style=discord.TextStyle.paragraph, max_length=4000)
    async def on_submit(self, interaction):
        try:
            data = json.loads(str(self.json_data))
            state = get_embed_state(interaction.user.id)
            state["titulo"] = data.get("title")
            state["descricao"] = data.get("description")
            state["cor"] = "#{:06x}".format(data.get("color", 0x5865F2))
            if data.get("author"): state["autor"] = data["author"].get("name")
            if data.get("footer"): state["rodape"] = data["footer"].get("text")
            if data.get("image"): state["imagem"] = data["image"].get("url")
            if data.get("thumbnail"): state["thumbnail"] = data["thumbnail"].get("url")
            state["campos"] = [{"nome": f["name"], "valor": f["value"]} for f in data.get("fields", [])]
            await interaction.response.edit_message(embed=build_embed_preview(state), view=EmbedPainelView(interaction.user.id))
        except Exception as e:
            await interaction.response.send_message(f"Erro: {e}", ephemeral=True)

class EmbedPainelView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        self.user_id = user_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Este painel nao e teu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Titulo", emoji="📝", style=discord.ButtonStyle.secondary, row=0)
    async def btn_titulo(self, interaction, button): await interaction.response.send_modal(ModalETitulo())

    @discord.ui.button(label="Descricao", emoji="📄", style=discord.ButtonStyle.secondary, row=0)
    async def btn_desc(self, interaction, button): await interaction.response.send_modal(ModalEDescricao())

    @discord.ui.button(label="Cor", emoji="🎨", style=discord.ButtonStyle.secondary, row=0)
    async def btn_cor(self, interaction, button): await interaction.response.send_modal(ModalECor())

    @discord.ui.button(label="Autor", emoji="👤", style=discord.ButtonStyle.secondary, row=0)
    async def btn_autor(self, interaction, button): await interaction.response.send_modal(ModalEAutor())

    @discord.ui.button(label="Campos", emoji="✏️", style=discord.ButtonStyle.secondary, row=1)
    async def btn_campos(self, interaction, button): await interaction.response.send_modal(ModalECampo())

    @discord.ui.button(label="Imagem", emoji="🖼️", style=discord.ButtonStyle.secondary, row=1)
    async def btn_imagem(self, interaction, button): await interaction.response.send_modal(ModalEImagem())

    @discord.ui.button(label="Rodape", emoji="🏳️", style=discord.ButtonStyle.secondary, row=1)
    async def btn_rodape(self, interaction, button): await interaction.response.send_modal(ModalERodape())

    @discord.ui.button(label="Importar JSON", emoji="⬆️", style=discord.ButtonStyle.primary, row=2)
    async def btn_importar(self, interaction, button): await interaction.response.send_modal(ModalEImportarJSON())

    @discord.ui.button(label="Exportar JSON", emoji="⬇️", style=discord.ButtonStyle.primary, row=2)
    async def btn_exportar(self, interaction, button):
        state = get_embed_state(interaction.user.id)
        data = build_embed_preview(state).to_dict()
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        await interaction.response.send_message(f"```json\n{json_str[:1900]}\n```", ephemeral=True)

    @discord.ui.button(label="Limpar", emoji="↩️", style=discord.ButtonStyle.danger, row=2)
    async def btn_limpar(self, interaction, button):
        if interaction.user.id in embed_states: del embed_states[interaction.user.id]
        state = get_embed_state(interaction.user.id)
        await interaction.response.edit_message(embed=build_embed_preview(state), view=EmbedPainelView(interaction.user.id))

    @discord.ui.button(label="Enviar Embed", emoji="🚀", style=discord.ButtonStyle.success, row=3)
    async def btn_enviar(self, interaction, button):
        state = get_embed_state(interaction.user.id)
        await interaction.channel.send(embed=build_embed_preview(state))
        await interaction.response.send_message("Embed enviado!", ephemeral=True)

# ============================================================
#  SLASH COMMANDS
# ============================================================
@bot.tree.command(name="embed", description="Abre o painel de criacao de embeds")
@app_commands.choices(acao=[app_commands.Choice(name="criar", value="criar")])
async def slash_embed(interaction, acao: app_commands.Choice[str]):
    if interaction.user.id in embed_states: del embed_states[interaction.user.id]
    state = get_embed_state(interaction.user.id)
    await interaction.response.send_message(content="**Painel de Criacao de Embed**",
        embed=build_embed_preview(state), view=EmbedPainelView(interaction.user.id), ephemeral=True)

@bot.tree.command(name="ticket_config", description="Configurar o sistema de tickets (admin)")
async def slash_ticket_config(interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Apenas admins!", ephemeral=True)
    await interaction.response.send_message(embed=build_config_embed(), view=ConfigView(), ephemeral=True)

@bot.tree.command(name="ticket_painel", description="Publicar o painel de tickets (admin)")
async def slash_ticket_painel(interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Apenas admins!", ephemeral=True)
    config = get_config()
    try:
        cor_int = int(config["cor"].lstrip("#"), 16)
    except:
        cor_int = 0x5865F2
    embed = discord.Embed(title=config["titulo"], description=config["descricao"], color=cor_int)
    await interaction.channel.send(embed=embed, view=CategoriasView(config["categorias"]))
    await interaction.response.send_message("Painel publicado!", ephemeral=True)

@bot.tree.command(name="ticket_stats", description="Estatisticas dos tickets (admin)")
async def slash_ticket_stats(interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Apenas admins!", ephemeral=True)
    tickets = get_tickets()
    total = len(tickets)
    abertos = sum(1 for t in tickets.values() if t.get("status") == "aberto")
    avaliacoes = [t["avaliacao"] for t in tickets.values() if t.get("avaliacao")]
    media = round(sum(avaliacoes)/len(avaliacoes), 1) if avaliacoes else "Sem dados"
    embed = discord.Embed(title="Estatisticas de Tickets", color=0x5865F2)
    embed.add_field(name="Total", value=total, inline=True)
    embed.add_field(name="Abertos", value=abertos, inline=True)
    embed.add_field(name="Fechados", value=total-abertos, inline=True)
    embed.add_field(name="Avaliacao Media", value=f"⭐ {media}" if avaliacoes else "Sem dados", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! **{round(bot.latency*1000)}ms**")

# ============================================================
#  INICIA
# ============================================================
bot.run(TOKEN)
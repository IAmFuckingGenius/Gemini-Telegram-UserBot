# Gemini UserBot for Telegram

![GitHub top language](https://img.shields.io/github/languages/top/VotisMUV/Gemini-Telegram-UserBot?style=for-the-badge&logo=python)
![MIT License](https://img.shields.io/github/license/VotisMUV/Gemini-Telegram-UserBot?style=for-the-badge)

This isn't just another API wrapper. This is a deeply integrated AI powerhouse designed to live in your personal Telegram account.

It transforms your account into a command center for AI-driven tasks, offering tools and flexibility that go far beyond basic Q&A bots.

---

## ✨ What Makes This Bot Different?

Instead of a boring feature list, here's what this bot actually lets you do.

### 🛠️ Tools on Steroids: Go Beyond Simple Chat
The bot's real power comes from its ability to use tools on the fly. It can interact with the world to get things done.
- **Get Real Answers:** Ask about current events or ask it to fact-check something. It will use Google Search to find up-to-date information instead of giving you a canned "my knowledge cut-off is..." response.
- **Become a Content Pro:** Drop a YouTube link and ask it to "summarize this video" or "download the audio." It'll process the content for you.
- **Generate AI Media:** Turn your ideas into reality. `??gem draw a photorealistic smart man with glasses download wallpaper` and it will generate an image using Imagen. You can even generate video clips.

### 🧠 Stop the Amnesia: True Context with Sessions
Tired of your AI forgetting what you were talking about five minutes ago? This bot solves that with isolated chat sessions.
- **Juggle Multiple Projects:** Create separate contexts with `??chat create work-project` and `??chat create vacation-planning`.
- **Switch Seamlessly:** Just type `??chat switch work-project`, and the bot instantly remembers every detail of that specific conversation.
- Manage, rename, and get stats for each session. It's like having multiple, specialized AIs at your fingertips.

### ⚙️ Future-Proof & Flexible: Dynamic Model Switching
The AI landscape changes weekly. This bot is built for it.
- **Swap Models On-the-Fly:** As an admin, you can switch the underlying AI model with a single Telegram command.
- **`??model chat gemini-2.5-flash`** and the bot immediately starts using the new, faster model for all future responses.
- **No restarts. No editing config files.** Just pure flexibility.

### 🌐 Built for Everyone: Fully Localized
The entire bot interface, from command replies to error messages, is controlled by simple JSON files.
- It comes with English and Russian out of the box.
- Want to add another language? Just copy `en_US.json`, translate the values, and you're good to go.

---

## 🚀 Getting Started

**Prerequisites:**
- Python 3.10+
- Git

**Step-by-Step:**

1.  **Clone the Repo:**
    ```bash
    git clone https://github.com/VotisMUV/Gemini-Telegram-UserBot.git
    cd Gemini-Telegram-UserBot
    ```

2.  **Set Up Your Environment (Highly Recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows, use: venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **IMPORTANT: Setup**

* You’ll find a template named `.env.example` in the repository. Create a copy and rename it to `.env`:

  ```bash
  cp .env.example .env
  ```
* Open the newly created `.env` file in your preferred editor.
* Replace **every** placeholder with your actual credentials (API keys, Telegram IDs, etc.).

5.  **Run the Bot:**
    ```bash
    python3 main.py
    ```
    On the first run, Telethon will prompt you for your phone number, a login code from Telegram, and possibly your 2FA password to create your personal `.session` file.

---

## 📖 Command Reference

The default prefix is `??`.

| Command | Description | Example Usage |
| :--- | :--- | :--- |
| **`??gem`** | The main command to talk to the AI. Supports files and tools. | `??gem refactor this python script for me` + attach `my_script.py` |
| **`??chat`** | Manage your conversation sessions. | `??chat create project-alpha`, then `??chat list` |
| **`??inst`** | Customize the bot's personality. Give it a system prompt to define *how* it should respond. | `??inst set You are a cynical old-school programmer. Be sarcastic.` |
| **`??clear`** | Wipes the conversation history for your **current** session. | `??clear` |
| **`??model`** | **(Admin Only)** View or change the active AI models on the fly. | `??model image *model-id*` |
| **`??help`** | Displays a detailed list of all commands and sub-commands. | `??help` |


---

## 📜 License

This project is released under the MIT License. See the [LICENSE](LICENSE) file for more details.

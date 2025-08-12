# 🎤 TikTok Live Stream Text-to-Speech AI Auto-Reply

An intelligent Django-based application that monitors TikTok live streams in real-time and automatically responds to comments, gifts, follows, and other interactions using AI-powered text-to-speech technology.

## 🌟 Features

- **Real-time TikTok Live Monitoring** - Connects to TikTok live streams and monitors all user interactions
- **AI-Powered Auto Responses** - Intelligent responses to comments using Google Gemini AI
- **Text-to-Speech Integration** - Converts responses to speech using ElevenLabs TTS API
- **Product Promotion** - Automatically detects product-related keywords and promotes your products
- **Multi-Event Support** - Handles comments, likes, gifts, follows, shares, and subscriptions
- **Rate Limit Management** - Smart API key rotation and quota management
- **Real-time Dashboard** - Live monitoring dashboard with event streaming
- **Audio File Management** - Automatic cleanup of generated audio files

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Django 4.0+
- ElevenLabs API Keys
- Google Gemini API access

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/tiennho2608/Text-to-Speech-AI-Automatic-Reply-for-TikTok-Livestream-Comments.git
   cd Text-to-Speech-AI-Automatic-Reply-for-TikTok-Livestream-Comments
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Django settings**
   ```bash
   python manage.py migrate
   python manage.py collectstatic
   ```

4. **Set up your API keys**
   - Get ElevenLabs API keys from [ElevenLabs](https://elevenlabs.io/)
   - Configure your voice ID from ElevenLabs voice library
   - Set up Google Gemini AI access

5. **Run the application**
   ```bash
   python manage.py runserver
   ```

6. **Access the dashboard**
   - Open `http://localhost:8000/dashboard/` in your browser

## 📋 API Configuration

### ElevenLabs TTS Setup

The application uses ElevenLabs for high-quality text-to-speech conversion:

```python
# Multiple API keys supported for rate limit management
api_keys = [
    "your_elevenlabs_api_key_1",
    "your_elevenlabs_api_key_2",
    "your_elevenlabs_api_key_3"
]

# Voice ID from ElevenLabs
voice_id = "21m00Tcm4TlvDq8ikWAM"  # Default voice
```

### Rate Limiting Features

- **Smart Key Rotation**: Automatically switches between API keys
- **Quota Management**: Tracks usage and handles quota limits
- **Cooldown Periods**: Implements waiting periods for rate-limited keys
- **Request Throttling**: 3-second intervals between requests, max 10/minute

## 🎯 Usage

### Starting a Monitor

1. Go to the dashboard at `/dashboard/`
2. Enter the TikTok username (without @)
3. Add your ElevenLabs API keys
4. Select voice ID (optional)
5. Click "Start Monitor"

### Monitor Features

- **Comment Responses**: Responds to every 2nd comment with fun, engaging messages
- **Product Promotion**: Detects keywords related to skincare/beauty products and provides promotional responses
- **Gift Acknowledgments**: Thanks users for gifts with personalized messages
- **Follow Welcomes**: Welcomes new followers
- **Real-time Logging**: All events are logged and displayed in real-time

### API Endpoints

- `POST /api/start/` - Start monitoring a TikTok user
- `POST /api/stop/` - Stop monitoring
- `GET /api/status/` - Get monitor status
- `GET /logs/<username>/` - Stream real-time logs
- `GET /audio/<filename>/` - Serve generated audio files

## 🛠️ Technical Architecture

### Core Components

1. **DjangoTikTokLiveMonitor**: Main monitoring class
2. **ElevenLabsTTS**: TTS engine with multi-key support
3. **ProductPromoter**: Keyword-based product promotion
4. **CommentResponder**: Fun response generation
5. **Real-time Event Streaming**: Server-sent events for live updates

### Event Handling

The application handles these TikTok live events:
- 💬 Comments
- ❤️ Likes  
- 🎁 Gifts
- 👤 Follows
- 🔗 Shares
- ⭐ Subscriptions
- 🔴 Live End

### Audio Management

- Automatic file cleanup (keeps max 15 files)
- MP3 format with optimized quality
- Cleanup of 10 oldest files when limit reached

## ⚙️ Configuration Options

### Product Promotion Keywords

The system automatically detects these keywords for product promotion:

```python
product_keywords = [
    'kem chống nắng', 'kem chong nang', 'sunscreen', 
    'kem dưỡng da', 'skincare', 'làm đẹp', 
    'chăm sóc da', 'da', 'mỹ phẩm', 'beauty', 'giá'
]
```

### TTS Settings

- **Model**: `eleven_flash_v2_5` (fast, high-quality)
- **Max Text Length**: 500 characters
- **Audio Format**: MP3
- **Response Conditions**: Only responds to comments ≤100 characters

## 📊 Monitoring & Logging

### Log Features

- **Real-time Event Streaming**: Live dashboard updates
- **Comprehensive Logging**: All events logged with timestamps
- **Error Handling**: Graceful error recovery and reconnection
- **Performance Metrics**: Track comment counts, TTS generations

### Dashboard Interface

- Live event feed
- Connection status
- Audio playback for generated responses
- Start/stop controls
- Real-time statistics

## 🔧 Advanced Features

### Auto-Reconnection

- Automatic reconnection on disconnects
- Max 5 reconnection attempts
- Exponential backoff (5s, 10s, 15s, 20s, 30s)
- Live status checking before reconnection

### Multi-Threading Support

- Async event handling
- Non-blocking TTS generation
- Concurrent monitor management
- Thread-safe logging

## 📁 Project Structure

```
Text-to-Speech-AI-Automatic-Reply-for-TikTok-Livestream-Comments/
├── liveapp/                    # Main Django app
│   ├── views.py               # Core monitoring logic
│   ├── urls.py                # URL routing
│   └── templates/             # Dashboard templates
├── tiktoklive/                # TikTok integration
├── media/audio/               # Generated audio files
├── logs/                      # Application logs
└── manage.py                  # Django management
```

## 🚨 Important Notes

### Rate Limits & Quotas

- ElevenLabs has API quotas - use multiple keys for extended operation
- TikTok connection limits - monitor responsibly
- Implement delays between responses to avoid spam detection

### Legal Considerations

- Ensure compliance with TikTok's Terms of Service
- Respect content creators and their communities
- Use responsibly for legitimate business purposes only

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is for educational and legitimate business use only. Please ensure compliance with all relevant terms of service.

## 🔗 Dependencies

- `TikTokLive` - TikTok live stream connection
- `ElevenLabs` - Text-to-speech API
- `Google Gemini` - AI response generation
- `Django` - Web framework
- `asyncio` - Asynchronous programming
- `threading` - Multi-threading support

## 📞 Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check the logs directory for debugging information
- Ensure all API keys are properly configured

---

**⚠️ Disclaimer**: This tool is designed for legitimate business and educational purposes. Users are responsible for ensuring compliance with TikTok's Terms of Service and applicable laws in their jurisdiction.

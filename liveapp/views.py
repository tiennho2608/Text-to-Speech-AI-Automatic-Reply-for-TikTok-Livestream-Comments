from django.shortcuts import render
import datetime as dt
import zipfile
from .tiktok_monitor import TikTokLiveMonitor, GeminiTTS
from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET
import json
import asyncio
import threading
import time
import queue
import os
import wave
import re
import random
from datetime import datetime
from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    ConnectEvent, DisconnectEvent, CommentEvent, LikeEvent, 
    GiftEvent, FollowEvent, ShareEvent, SubscribeEvent,
    LiveEndEvent
)
from google import genai
from google.genai import types
import logging

# Create your views here.
class ElevenLabsTTS:
    def __init__(self, api_keys: list, voice_id: str):
        if isinstance(api_keys, str):
            api_keys = [api_keys]
        
        self.api_keys = api_keys
        self.voice_id = voice_id  # ElevenLabs voice ID
        self.current_key_index = 0
        self.clients = {}
        self.key_last_used = {}
        self.key_request_count = {}
        self.key_quota_exhausted = {}
        self.key_quota_reset_time = {}
        self.failed_keys = set()
        self._lock = threading.Lock()
        
        # Audio file management settings
        self.audio_dir = 'media/audio'
        self.max_audio_files = 15  # Changed to 15 files
        self.cleanup_count = 10   # Delete 10 oldest files when limit reached
        
        # Initialize ElevenLabs clients for each API key
        print(f"🔧 [TTS] Khởi tạo {len(self.api_keys)} ElevenLabs API Keys...")
        for i, key in enumerate(self.api_keys):
            try:
                print(f"🔑 [TTS] Đang khởi tạo ElevenLabs API Key {i+1}...")
                self.clients[i] = ElevenLabs(api_key=key)
                self.key_last_used[i] = 0
                self.key_request_count[i] = 0
                self.key_quota_exhausted[i] = False
                self.key_quota_reset_time[i] = datetime.now()
                print(f"✅ [TTS] ElevenLabs API Key {i+1} khởi tạo THÀNH CÔNG!")
                logging.info(f"ElevenLabs API Key {i+1} initialized successfully")
            except Exception as e:
                print(f"❌ [TTS] ElevenLabs API Key {i+1} FAILED: {e}")
                logging.error(f"ElevenLabs API Key {i+1} failed: {e}")
                self.failed_keys.add(i)
        
        # Rate limits for ElevenLabs
        self.request_interval = 3
        self.max_requests_per_minute = 10
        self.quota_reset_interval = 3600
        
        print(f"⚙️  [TTS] ElevenLabs Rate limits: {self.request_interval}s interval, {self.max_requests_per_minute} req/min")
        print(f"🗂️  [TTS] Audio settings: Max {self.max_audio_files} files, cleanup {self.cleanup_count} oldest")
        print(f"🎤 [TTS] Voice ID: {self.voice_id}")
        
        working_keys = len(self.api_keys) - len(self.failed_keys)
        print(f"🔑 [TTS] Keys status: {working_keys}/{len(self.api_keys)} working")
        print(f"=" * 60)
        
    def mark_quota_exhausted(self, key_index):
        self.key_quota_exhausted[key_index] = True
        self.key_quota_reset_time[key_index] = datetime.now()
        print(f"🚫 [TTS] ElevenLabs API Key {key_index+1} đã bị QUOTA EXHAUSTED!")
        logging.warning(f"ElevenLabs API Key {key_index+1} marked as quota exhausted")
        
    def reset_quota_if_needed(self, key_index):
        current_time = datetime.now()
        if (self.key_quota_exhausted[key_index] and 
            current_time - self.key_quota_reset_time[key_index] > timedelta(seconds=self.quota_reset_interval)):
            self.key_quota_exhausted[key_index] = False
            self.key_request_count[key_index] = 0
            print(f"🔄 [TTS] ElevenLabs API Key {key_index+1} QUOTA RESET sau cooldown!")
            logging.info(f"ElevenLabs API Key {key_index+1} quota status reset after cooldown")
        
    def can_speak_now(self) -> bool:
        current_time = time.time()
        with self._lock:
            for key_index in range(len(self.api_keys)):
                if key_index in self.failed_keys:
                    continue
                self.reset_quota_if_needed(key_index)
                if self.key_quota_exhausted[key_index]:
                    continue
                time_since_last = current_time - self.key_last_used[key_index]
                requests_used = self.key_request_count[key_index]
                if time_since_last > 60:
                    self.key_request_count[key_index] = 0
                    requests_used = 0
                if (time_since_last >= self.request_interval and 
                    requests_used < self.max_requests_per_minute):
                    return True
        return False
    
    def generate_audio(self, text: str):
        print(f"\n🎤 [TTS] Bắt đầu generate audio với ElevenLabs...")
        print(f"📝 [TTS] Text length: {len(text)} chars")
        max_retries = len(self.api_keys)
        retry_count = 0
        max_wait_retries = 3
        wait_retry_count = 0
        while retry_count < max_retries:
            try:
                print(f"🔄 [TTS] Attempt {retry_count+1}/{max_retries}")
                if not self.can_speak_now():
                    if wait_retry_count < max_wait_retries:
                        wait_retry_count += 1
                        print(f"🚫 [TTS] Không thể generate: Tất cả ElevenLabs keys bị rate limit hoặc quota exhausted")
                        print(f"⏳ [TTS] Đợi 5s và thử lại (Wait attempt {wait_retry_count}/{max_wait_retries})...")
                        logging.warning(f"Cannot generate audio: all ElevenLabs keys rate limited or quota exhausted. Waiting 5s (attempt {wait_retry_count}/{max_wait_retries})")
                        time.sleep(5)
                        continue
                    else:
                        print(f"💀 [TTS] Đã thử đợi {max_wait_retries} lần, tất cả ElevenLabs keys vẫn bị limit")
                        logging.error("Cannot generate audio: all ElevenLabs keys still rate limited after waiting")
                        return None
                key_index = self.get_next_available_key()
                if key_index is None:
                    print(f"💀 [TTS] Không có ElevenLabs API key nào khả dụng!")
                    logging.error("No available ElevenLabs API keys for TTS")
                    return None
                print(f"🔑 [TTS] Sử dụng ElevenLabs API Key {key_index+1}")
                client = self.clients[key_index]
                clean_text = re.sub(r'[^\w\s\u00C0-\u017F\u1E00-\u1EFF\u2000-\u206F\u2070-\u209F\u20A0-\u20CF\u2100-\u214F\u2190-\u21FF\u2200-\u22FF]', ' ', text)
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                if not clean_text or len(clean_text) < 3:
                    print(f"⚠️  [TTS] Text quá ngắn hoặc rỗng")
                    logging.warning("Text too short or empty for TTS")
                    return None
                if len(clean_text) > 500:
                    clean_text = clean_text[:500] + "..."
                    print(f"✂️  [TTS] Text bị cắt xuống 500 chars")
                print(f"🚀 [TTS] Gửi request đến ElevenLabs API Key {key_index+1}...")
                logging.debug(f"Generating TTS with ElevenLabs API Key {key_index+1}")
                start_time = time.time()
                audio_stream = client.text_to_speech.convert(
                    voice_id=self.voice_id,
                    model_id="eleven_flash_v2_5",
                    text=clean_text
                )
                response_time = time.time() - start_time
                print(f"⚡ [TTS] ElevenLabs API Key {key_index+1} phản hồi trong {response_time:.2f}s")
                with self._lock:
                    self.key_last_used[key_index] = time.time()
                    self.key_request_count[key_index] += 1
                    new_count = self.key_request_count[key_index]
                    print(f"📈 [TTS] ElevenLabs API Key {key_index+1}: Request count {new_count}/{self.max_requests_per_minute}")
                os.makedirs(self.audio_dir, exist_ok=True)
                filename = f"{self.audio_dir}/tts_{key_index}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.mp3"
                with open(filename, "wb") as f:
                    for chunk in audio_stream:
                        f.write(chunk)
                audio_size = os.path.getsize(filename)
                print(f"🎵 [TTS] Nhận được audio data: {audio_size} bytes")
                print(f"💾 [TTS] File saved: {os.path.basename(filename)}")
                print(f"✅ [TTS] THÀNH CÔNG với ElevenLabs API Key {key_index+1}")
                logging.info(f"ElevenLabs TTS audio generated: {filename} (API Key {key_index+1})")
                self.cleanup_old_audio_files()
                return filename
            except Exception as e:
                error_msg = str(e).lower()
                print(f"💥 [TTS] LỖI với ElevenLabs API Key {key_index+1}: {str(e)}")
                logging.error(f"ElevenLabs TTS Error with key {key_index+1}: {e}")
                if any(quota_keyword in error_msg for quota_keyword in ['quota', 'limit', 'exceeded', 'rate limit', 'usage']):
                    print(f"🚫 [TTS] ElevenLabs API Key {key_index+1}: QUOTA LIMIT HIT!")
                    logging.warning(f"ElevenLabs API Key {key_index+1} hit quota limit")
                    self.mark_quota_exhausted(key_index)
                else:
                    print(f"⚠️  [TTS] ElevenLabs API Key {key_index+1}: Tạm thời FAILED (2 phút)")
                    self.failed_keys.add(key_index)
                    threading.Timer(120, lambda: self.failed_keys.discard(key_index)).start()
                retry_count += 1
                if retry_count < max_retries:
                    print(f"🔁 [TTS] Thử lại với ElevenLabs key khác (attempt {retry_count+1}/{max_retries})")
                    logging.info(f"Retrying with next available ElevenLabs key (attempt {retry_count+1}/{max_retries})")
                    time.sleep(0.5)
        print(f"💀 [TTS] TẤT CẢ ELEVENLABS API KEYS ĐỀU THẤT BẠI!")
        logging.error("All ElevenLabs API keys exhausted or failed for TTS generation")
        return None

    def get_key_status(self):
        status = {}
        current_time = datetime.now()
        for i in range(len(self.api_keys)):
            status[f"key_{i+1}"] = {
                "failed": i in self.failed_keys,
                "quota_exhausted": self.key_quota_exhausted[i],
                "request_count": self.key_request_count[i],
                "last_used": datetime.fromtimestamp(self.key_last_used[i]).strftime('%H:%M:%S') if self.key_last_used[i] > 0 else "Never",
                "quota_reset_in": max(0, int((self.key_quota_reset_time[i] + timedelta(seconds=self.quota_reset_interval) - current_time).total_seconds())) if self.key_quota_exhausted[i] else 0,
                "voice_id": self.voice_id
            }
        return status
        
    def reset_all_quotas(self):
        with self._lock:
            for i in range(len(self.api_keys)):
                if i not in self.failed_keys:
                    self.key_quota_exhausted[i] = False
                    self.key_request_count[i] = 0
                    self.key_quota_reset_time[i] = datetime.now()
        logging.info("All ElevenLabs API key quotas manually reset")
        
    def get_audio_files_count(self):
        try:
            audio_pattern = os.path.join(self.audio_dir, "tts_*.mp3")
            return len(glob.glob(audio_pattern))
        except Exception as e:
            logging.error(f"Error counting audio files: {e}")
            return 0

    def set_voice(self, voice_id: str):
        self.voice_id = voice_id
        print(f"🎤 [TTS] Voice ID changed to: {voice_id}")
        logging.info(f"ElevenLabs voice ID changed to: {voice_id}")

class UnicodeStreamHandler(logging.StreamHandler):
    def __init__(self, stream=None):
        super().__init__(stream)
        
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            if hasattr(stream, 'buffer'):
                stream.buffer.write(msg.encode('utf-8', errors='replace') + b'\n')
                stream.buffer.flush()
            else:
                safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
                stream.write(safe_msg + '\n')
                if hasattr(stream, 'flush'):
                    stream.flush()
        except Exception:
            self.handleError(record)

def setup_logging():
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    simple_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    file_handler = logging.FileHandler(
        f'{log_dir}/tiktok_monitor_{datetime.now().strftime("%Y%m%d")}.log',
        encoding='utf-8',
        mode='a'
    )
    file_handler.setFormatter(detailed_formatter)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    console_handler = UnicodeStreamHandler(sys.stdout)
    console_handler.setFormatter(simple_formatter)
    console_handler.setLevel(logging.WARNING)
    root_logger.addHandler(console_handler)
    tiktok_logger = logging.getLogger('tiktok_monitor')
    tiktok_logger.setLevel(logging.INFO)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    return tiktok_logger

logger = setup_logging()

def safe_log_event(logger, level, username, event_data):
    try:
        safe_event = {}
        for key, value in event_data.items():
            if isinstance(value, str):
                safe_value = value.encode('ascii', errors='replace').decode('ascii')
                safe_event[key] = safe_value
            else:
                safe_event[key] = value
        message = f"Event for {username}: {safe_event}"
        logger.log(level, message)
    except Exception as e:
        logger.error(f"Logging error: {e}")

def safe_event_stream(username, log_queue, active_monitors):
    while username in active_monitors:
        try:
            event = log_queue.get(timeout=1)
            safe_event = dict(event)
            if 'message' in safe_event and isinstance(safe_event['message'], str):
                safe_event['message'] = safe_event['message'].encode('utf-8', errors='replace').decode('utf-8')
            logger = logging.getLogger('tiktok_monitor')
            safe_log_event(logger, logging.INFO, username, safe_event)
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            log_queue.task_done()
        except queue.Empty:
            keepalive = {
                'type': 'keepalive', 
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
            yield f"data: {json.dumps(keepalive)}\n\n"
        except Exception as e:
            error_event = {
                'type': 'error', 
                'message': f'Streaming error: {str(e)}',
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
            yield f"data: {json.dumps(error_event)}\n\n"
            break

class ProductPromoter:
    def __init__(self):
        self.product_keywords = [
            'kem chống nắng', 'kem chong nang', 'sunscreen', 
            'kem dưỡng da', 'skincare', 'làm đẹp', 
            'chăm sóc da', 'da', 'mỹ phẩm', 'beauty', 'giá'
        ]
    
    def should_promote(self, comment: str) -> bool:
        comment_lower = comment.lower()
        return any(keyword in comment_lower for keyword in self.product_keywords)
    
    def get_promotion_message(self) -> str:
        return """Cảm ơn bạn quan tâm đến kem chống nắng! 
        Sản phẩm kem chống nắng của chúng tôi có những ưu điểm vượt trội:
        - Bảo vệ da khỏi tia UV hiệu quả
        - Thành phần tự nhiên, an toàn cho mọi loại da  
        - Không gây bết dính, thẩm thấu nhanh
        - Có khả năng chống nước, bền màu cả ngày
        - Giá đặc biệt chỉ 60,000 VNĐ
        Liên hệ ngay để đặt hàng và nhận ưu đãi hấp dẫn!"""

class CommentResponder:
    def __init__(self):
        self.fun_responses = [
            "Haha bạn nói hay quá!",
            "Cảm ơn bạn đã comment nhé!",
            "Bạn thật là dễ thương!",
            "Wow, comment này hay lắm!",
            "Bạn có vẻ rất vui tính đấy!",
            "Thanks bạn, mình rất vui!",
            "Bạn làm mình cười rồi!",
            "Comment của bạn làm mình vui lắm!",
            "Bạn thật tuyệt vời!",
            "Hehe, bạn nói đúng rồi!"
        ]
        self.gift_responses = [
            "Wow, cảm ơn {username} đã tặng {gift_name}! Bạn thật tuyệt vời!",
            "{username} ơi, quà {gift_name} của bạn làm mình siêu vui!",
            "Cảm ơn {username} đã tặng {gift_name}! Yêu bạn nhiều lắm!",
            "Ôi, {gift_name} từ {username}! Cảm ơn bạn, mình cảm động quá!",
            "{username}, quà {gift_name} của bạn thật đặc biệt! Cảm ơn nhé!"
        ]
    
    def get_fun_response(self, username: str) -> str:
        response = random.choice(self.fun_responses)
        return f"{username} ơi! {response}"
    
    def get_gift_response(self, username: str, gift_name: str) -> str:
        response = random.choice(self.gift_responses)
        return response.format(username=username, gift_name=gift_name)

class DjangoTikTokLiveMonitor:
    def __init__(self, unique_id: str, api_keys: list, voice_id: str, log_queue: queue.Queue):
        self.client = TikTokLiveClient(unique_id=unique_id)
        self.client.logger.setLevel('WARNING')
        self.log_queue = log_queue
        self.promoter = ProductPromoter()
        self.responder = CommentResponder()
        self.tts = ElevenLabsTTS(api_keys, voice_id=voice_id)
        self.comment_count = 0
        self.like_count = 0
        self.tts_count = 0
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.setup_event_handlers()
    
    def setup_event_handlers(self):
        @self.client.on(ConnectEvent)
        async def on_connect(event: ConnectEvent):
            self.running = True
            self.reconnect_attempts = 0
            log_entry = {
                'type': 'connect',
                'message': f"Connected to @{event.unique_id} (Room ID: {self.client.room_id})",
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
            self.log_queue.put(log_entry)
        
        @self.client.on(DisconnectEvent)
        async def on_disconnect(event: DisconnectEvent):
            was_running = self.running
            self.running = False
            log_entry = {
                'type': 'disconnect',
                'message': f"Disconnected from @{self.client.unique_id}",
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
            self.log_queue.put(log_entry)
            if was_running and self.reconnect_attempts < self.max_reconnect_attempts:
                await self._attempt_reconnect()
        
        @self.client.on(CommentEvent)
        async def on_comment(event: CommentEvent):
            try:
                self.comment_count += 1
                username = event.user.nickname
                comment = event.comment
                log_entry = {
                    'type': 'comment',
                    'message': f"[{self.comment_count}] {username}: {comment}",
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                }
                self.log_queue.put(log_entry)
                if self.comment_count % 2 == 0:
                    if self.promoter.should_promote(comment):
                        response = self.promoter.get_promotion_message()
                        await self._send_response(response, 'promotion')
                    elif len(comment) <= 100:
                        response = self.responder.get_fun_response(username)
                        await self._send_response(response, 'response')
            except Exception as e:
                logger.error(f"Error handling comment: {e}")
        
        @self.client.on(LikeEvent)
        async def on_like(event: LikeEvent):
            try:
                self.like_count += 1
                username = event.user.nickname
                like_count = getattr(event, 'count', 1)
                log_entry = {
                    'type': 'like',
                    'message': f"[{self.like_count}] {username} liked (x{like_count})",
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                }
                self.log_queue.put(log_entry)
            except Exception as e:
                logger.error(f"Error handling like: {e}")
        
        @self.client.on(GiftEvent)
        async def on_gift(event: GiftEvent):
            try:
                username = event.user.nickname
                gift_name = event.gift.name
                count = event.repeat_count
                message = f"{username} sent {count}x {gift_name}" if event.gift.streakable and not event.streaking else f"{username} sent {gift_name}"
                log_entry = {
                    'type': 'gift',
                    'message': message,
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                }
                self.log_queue.put(log_entry)
                response = self.responder.get_gift_response(username, gift_name)
                await self._send_response(response, 'response')
            except Exception as e:
                logger.error(f"Error handling gift: {e}")
        
        @self.client.on(FollowEvent)
        async def on_follow(event: FollowEvent):
            try:
                username = event.user.nickname
                log_entry = {
                    'type': 'follow',
                    'message': f"{username} followed the streamer!",
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                }
                self.log_queue.put(log_entry)
                response = f"Cảm ơn {username} đã follow! Chào mừng đến với kênh của mình!"
                await self._send_response(response, 'response')
            except Exception as e:
                logger.error(f"Error handling follow: {e}")
        
        @self.client.on(ShareEvent)
        async def on_share(event: ShareEvent):
            try:
                username = event.user.nickname
                log_entry = {
                    'type': 'share',
                    'message': f"{username} shared the livestream!",
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                }
                self.log_queue.put(log_entry)
            except Exception as e:
                logger.error(f"Error handling share: {e}")
        
        @self.client.on(SubscribeEvent)
        async def on_subscribe(event: SubscribeEvent):
            try:
                username = event.user.nickname
                log_entry = {
                    'type': 'subscribe',
                    'message': f"{username} subscribed!",
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                }
                self.log_queue.put(log_entry)
            except Exception as e:
                logger.error(f"Error handling subscribe: {e}")
        
        @self.client.on(LiveEndEvent)
        async def on_live_end(event: LiveEndEvent):
            self.running = False
            log_entry = {
                'type': 'live_end',
                'message': "Livestream ended by streamer",
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
            self.log_queue.put(log_entry)
    
    async def _send_response(self, response: str, response_type: str):
        try:
            audio_file = None
            if len(response) <= 500 and self.tts.can_speak_now():
                audio_file = self.tts.generate_audio(response)
                if audio_file:
                    self.tts_count += 1
            log_entry = {
                'type': response_type,
                'message': response,
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'audio_file': audio_file
            }
            self.log_queue.put(log_entry)
        except Exception as e:
            logger.error(f"Error sending response: {e}")
    
    async def _attempt_reconnect(self):
        self.reconnect_attempts += 1
        wait_time = min(5 * self.reconnect_attempts, 30)
        log_entry = {
            'type': 'info',
            'message': f"Attempting to reconnect in {wait_time}s (Attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})",
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        self.log_queue.put(log_entry)
        await asyncio.sleep(wait_time)
        try:
            is_live = await self.client.is_live()
            if not is_live:
                self.log_queue.put({
                    'type': 'error',
                    'message': f"@{self.client.unique_id} is no longer live. Stopping reconnection attempts.",
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                })
                return
            task = await self.client.start()
            log_entry = {
                'type': 'info',
                'message': f"Reconnection attempt {self.reconnect_attempts} successful",
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
            self.log_queue.put(log_entry)
        except Exception as e:
            log_entry = {
                'type': 'error',
                'message': f"Reconnection attempt {self.reconnect_attempts} failed: {str(e)}",
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
            self.log_queue.put(log_entry)
            if self.reconnect_attempts < self.max_reconnect_attempts:
                await self._attempt_reconnect()
    
    async def start_monitoring(self):
        try:
            self.log_queue.put({
                'type': 'info',
                'message': f"Starting TikTok Live Monitor for @{self.client.unique_id}",
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
            is_live = await self.client.is_live()
            if not is_live:
                self.log_queue.put({
                    'type': 'error',
                    'message': f"@{self.client.unique_id} is not currently live",
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                })
                return
            self.log_queue.put({
                'type': 'info',
                'message': f"Live Status Check: LIVE ✅",
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
            task = await asyncio.wait_for(self.client.start(), timeout=300)
            await task
        except asyncio.TimeoutError:
            self.log_queue.put({
                'type': 'error',
                'message': f"Connection timeout after 5 minutes",
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
            await self.client.disconnect()
        except Exception as e:
            self.log_queue.put({
                'type': 'error',
                'message': f"Monitor error: {str(e)}",
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
            await self.client.disconnect()
            if self.running and self.reconnect_attempts < self.max_reconnect_attempts:
                await self._attempt_reconnect()
    
    async def stop_monitoring(self):
        self.running = False
        self.reconnect_attempts = self.max_reconnect_attempts
        try:
            await self.client.disconnect()
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
        self.log_queue.put({
            'type': 'info',
            'message': f"Stopped monitoring @{self.client.unique_id}",
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })

def monitor_dashboard(request):
    return render(request, 'monitor/dashboard.html')

@csrf_exempt
@require_http_methods(["POST"])
def start_monitor(request):
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        api_keys = data.get('api_keys', [])
        voice_id = data.get('voice_id', '21m00Tcm4TlvDq8ikWAM')
        
        logger.info(f"Starting monitor for username: {username}")
        
        if not username or not api_keys:
            logger.error("Username or API keys missing")
            return JsonResponse({'error': 'Username and API keys are required'}, status=400)
        
        if username.startswith('@'):
            username = username[1:]
        
        if username in active_monitors:
            logger.info(f"Stopping existing monitor for {username}")
            try:
                monitor = active_monitors[username]
                monitor.running = False
                def stop_monitor_async():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(monitor.stop_monitoring())
                    except Exception as e:
                        logger.warning(f"Error stopping old monitor: {e}")
                    finally:
                        loop.close()
                threading.Thread(target=stop_monitor_async, daemon=True).start()
            except Exception as e:
                logger.warning(f"Error stopping existing monitor: {e}")
            del active_monitors[username]
            if username in log_queues:
                del log_queues[username]
        
        log_queue = queue.Queue()
        log_queues[username] = log_queue
        monitor = DjangoTikTokLiveMonitor(username, api_keys, voice_id, log_queue)
        active_monitors[username] = monitor
        
        logger.info(f"Initialized monitor for {username}")
        
        def start_async_monitor():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                logger.info(f"Starting async monitor for {username}")
                loop.run_until_complete(monitor.start_monitoring())
            except Exception as e:
                logger.error(f"Error in async monitor for {username}: {e}")
            finally:
                loop.close()
        
        thread = threading.Thread(target=start_async_monitor, daemon=True)
        thread.start()
        
        time.sleep(1)
        
        logger.info(f"Monitor successfully started for {username}")
        return JsonResponse({
            'status': 'success',
            'message': f'Monitor started for @{username}',
            'username': username
        })
        
    except Exception as e:
        logger.error(f"Error starting monitor: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def stop_monitor(request):
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        
        logger.info(f"Attempting to stop monitor for {username}")
        
        if username.startswith('@'):
            username = username[1:]
        
        if username in active_monitors:
            try:
                monitor = active_monitors[username]
                monitor.running = False
                def stop_monitor_async():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(monitor.stop_monitoring())
                    except Exception as e:
                        logger.warning(f"Error in async stop: {e}")
                    finally:
                        loop.close()
                threading.Thread(target=stop_monitor_async, daemon=True).start()
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Error stopping monitor gracefully: {e}")
            
            del active_monitors[username]
            if username in log_queues:
                del log_queues[username]
                
            logger.info(f"Monitor stopped for {username}")
            return JsonResponse({
                'status': 'success',
                'message': f'Monitor stopped for @{username}'
            })
        else:
            logger.warning(f"No active monitor found for {username}")
            return JsonResponse({'error': 'No active monitor found'}, status=404)
            
    except Exception as e:
        logger.error(f"Error stopping monitor: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@require_GET
def serve_audio(request, filename):
    try:
        safe_filename = os.path.basename(filename)
        file_path = os.path.join('media', 'audio', safe_filename)
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='audio/mpeg')
                response['Content-Disposition'] = f'inline; filename="{safe_filename}"'
                response['Content-Length'] = os.path.getsize(file_path)
                return response
        else:
            return HttpResponse("Audio file not found", status=404)
    except Exception as e:
        return HttpResponse("Error serving audio file", status=500)
    
def cleanup_monitors():
    logger.info("Cleaning up active monitors...")
    for username, monitor in list(active_monitors.items()):
        try:
            monitor.running = False
        except Exception as e:
            logger.error(f"Error cleaning up monitor {username}: {e}")
    active_monitors.clear()
    log_queues.clear()
    logger.info("Cleanup complete")
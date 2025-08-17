from flask import Flask, request, jsonify, Response
from openai import OpenAI
from uuid import uuid4
from datetime import datetime, timedelta
import threading
import json
import random

app = Flask(__name__)

# 会话存储
sessions = {}
session_lock = threading.Lock()
SESSION_EXPIRE_HOURS = 2

# 初始化OpenAI客户端
client = OpenAI(
    api_key="sk-7a81f3d7726c4b5da64a172be92d8d52",
    base_url="https://api.deepseek.com/v1",
)

# 场景配置
SCENARIOS = {
    "campus": {
        "name": "校园生活",
        "description": "那些青春岁月里的美好回忆"
    },
    "love": {
        "name": "恋爱时光",
        "description": "甜蜜的爱情故事和浪漫瞬间"
    },
    "family": {
        "name": "家庭温暖",
        "description": "与家人共度的珍贵时光"
    },
    "friendship": {
        "name": "友谊岁月",
        "description": "与朋友们的难忘经历"
    },
    "travel": {
        "name": "旅行见闻",
        "description": "在路上遇见的美好风景"
    },
    "childhood": {
        "name": "童年记忆",
        "description": "无忧无虑的童年时光"
    }
}


def cleanup_expired_sessions():
    """清理过期的会话"""
    now = datetime.now()
    expired_sessions = []
    with session_lock:
        for session_id, session_data in sessions.items():
            if now - session_data['last_active'] > timedelta(hours=SESSION_EXPIRE_HOURS):
                expired_sessions.append(session_id)
        for session_id in expired_sessions:
            del sessions[session_id]


def generate_theme_words(scenario, refresh_count=0):
    """使用LLM生成主题词"""
    try:
        scenario_info = SCENARIOS.get(scenario, SCENARIOS["campus"])

        prompt = f"""请为"{scenario_info['name']}"场景生成20个适合用作回忆主题的词语。
要求：
1. 词语要有情感温度，能触发美好回忆
2. 每个词语2-4个字，简洁有力
3. 符合{scenario_info['description']}这个主题
4. 词语要有多样性，涵盖不同的情感和场景
5. 只返回词语列表，用逗号分隔，不要其他解释

示例格式：初见,心动,温暖,微笑,陪伴,成长,梦想,感动,拥抱,告别,重逢,青春,纯真,勇气,希望,眼泪,笑声,秘密,约定,永远"""

        # 如果是第三次刷新，允许重复
        if refresh_count >= 2:
            prompt += "\n注意：这是第三次刷新，可以包含一些之前出现过的优质主题词。"

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.3
        )

        words_text = response.choices[0].message.content.strip()
        words = [word.strip() for word in words_text.split(',') if word.strip()]

        # 确保有20个词语
        if len(words) < 20:
            # 如果不足20个，补充一些通用主题词
            backup_words = ["初见", "心动", "温暖", "微笑", "陪伴", "成长", "梦想", "感动", "拥抱", "告别"]
            words.extend(backup_words[:20 - len(words)])

        return words[:20]

    except Exception as e:
        # 如果API调用失败，返回默认主题词
        default_words = {
            "campus": ["初见", "心动", "课堂", "食堂", "图书馆", "社团", "考试", "毕业", "青春", "同窗", "老师", "操场",
                       "宿舍", "晚自习", "春游", "运动会", "文艺汇演", "奖学金", "友谊", "成长"],
            "love": ["心动", "初吻", "约会", "牵手", "拥抱", "告白", "甜蜜", "思念", "浪漫", "温柔", "陪伴", "承诺",
                     "眼神", "微笑", "心跳", "脸红", "惊喜", "礼物", "永远", "深情"],
            "family": ["温暖", "团圆", "妈妈", "爸爸", "爷爷", "奶奶", "兄弟", "姐妹", "年夜饭", "生日", "关怀", "唠叨",
                       "拥抱", "陪伴", "守护", "传承", "亲情", "回家", "思念", "感恩"],
            "friendship": ["知己", "陪伴", "聊天", "玩耍", "分享", "守护", "信任", "理解", "支持", "鼓励", "欢声",
                           "笑语", "秘密", "约定", "重逢", "思念", "珍惜", "真诚", "默契", "永远"],
            "travel": ["风景", "远方", "背包", "火车", "飞机", "酒店", "美食", "文化", "冒险", "自由", "日出", "日落",
                       "海浪", "山峰", "古镇", "异乡", "邂逅", "回忆", "照片", "足迹"],
            "childhood": ["玩具", "游戏", "糖果", "动画", "小伙伴", "捉迷藏", "跳绳", "滑梯", "秋千", "冰棍", "压岁钱",
                          "新衣服", "儿歌", "故事书", "幼儿园", "小学", "天真", "快乐", "无忧", "梦想"]
        }
        return default_words.get(scenario, default_words["campus"])


def get_fragment_title_with_number(fragments, base_title):
    """获取带数字后缀的标题，避免重复"""
    existing_titles = [f['title'] for f in fragments]

    if base_title not in existing_titles:
        return base_title

    counter = 2
    while f"{base_title}{counter}" in existing_titles:
        counter += 1

    return f"{base_title}{counter}"


@app.route('/get_scenarios', methods=['GET'])
def get_scenarios():
    """获取所有场景"""
    return jsonify({'scenarios': SCENARIOS})


@app.route('/get_theme_words', methods=['POST'])
def get_theme_words():
    """获取主题词 - 改为SSE流式响应"""
    data = request.json
    scenario = data.get('scenario', 'campus')
    refresh_count = data.get('refresh_count', 0)

    def generate():
        try:
            words = generate_theme_words(scenario, refresh_count)

            # 发送初始化事件
            yield "event: init\ndata: {}\n\n"

            # 模拟流式传输效果
            for i, word in enumerate(words):
                # 发送进度事件
                progress = {
                    'progress': (i + 1) / len(words) * 100,
                    'current': i + 1,
                    'total': len(words)
                }
                yield f"event: progress\ndata: {json.dumps(progress)}\n\n"

                # 发送单词事件
                yield f"event: word\ndata: {json.dumps({'word': word})}\n\n"

            # 发送完成事件
            yield "event: complete\ndata: {}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route('/create_fragment', methods=['POST'])
def create_fragment():
    """创建回忆碎片"""
    data = request.json
    session_id = data.get('session_id')
    theme_word = data.get('theme_word')

    if not session_id or not theme_word:
        return jsonify({'error': '缺少必要参数'}), 400

    cleanup_expired_sessions()

    with session_lock:
        if session_id not in sessions:
            sessions[session_id] = {
                'fragments': [],
                'last_active': datetime.now()
            }

        session = sessions[session_id]
        session['last_active'] = datetime.now()

        # 生成带数字后缀的标题
        title = get_fragment_title_with_number(session['fragments'], theme_word)

        # 创建新碎片
        fragment = {
            'id': str(uuid4()),
            'title': title,
            'theme_word': theme_word,
            'content': None,  # 未生成内容
            'timeline_date': None,  # 时间轴日期
            'created_at': datetime.now().isoformat(),
            'status': 'new'  # new, generated, edited
        }

        session['fragments'].append(fragment)

        return jsonify({
            'fragment': fragment,
            'fragment_id': fragment['id']
        })


@app.route('/generate_content', methods=['POST'])
def generate_content():
    """生成回忆内容 - 改为SSE流式响应，使用DeepSeek API"""
    data = request.json
    session_id = data.get('session_id')
    fragment_id = data.get('fragment_id') # 确保接收 fragment_id
    user_description = data.get('user_description', '') # 确保接收 user_description

    if not session_id or not fragment_id: # 检查 fragment_id
        return jsonify({'error': '缺少必要参数'}), 400

    def generate():
        try:
            # --- (查找 session 和 fragment 的逻辑保持不变) ---
            with session_lock:
                if session_id not in sessions:
                    yield f"event: error\ndata: {json.dumps({'error': '会话不存在'})}\n\n"
                    return
                session = sessions[session_id]
                fragment = next((f for f in session['fragments'] if f['id'] == fragment_id), None)
                if not fragment:
                    yield f"event: error\ndata: {json.dumps({'error': '碎片不存在'})}\n\n"
                    return
                # 更新状态为生成中
                fragment['status'] = 'generating'
                session['last_active'] = datetime.now()
            # --- (查找逻辑结束) ---

            # 发送开始事件
            yield "event: start\ndata: {}\n\n"

            # 构建提示词 - 使用传入的 user_description
            theme_word = fragment['theme_word']
            # 修改提示词构建，明确区分用户输入和主题词
            effective_description = user_description if user_description else f"请根据主题词'{theme_word}'创作一段回忆"
            prompt = f"""你是一个专业的回忆整理师，帮助用户将零散的记忆整理成优美的文字。
主题词：{theme_word}
用户的回忆片段：{effective_description}
请基于用户的回忆片段，创作一段关于"{theme_word}"的回忆文章。要求：
1.  文章要有温度和情感，能够触动人心
2.  保持真实感，不要过于华丽或虚假
3.  字数控制在300-800字之间
4.  结构清晰，有开头、发展和结尾
5.  融入具体的场景、人物、对话和感受
6.  体现这段回忆的珍贵和意义
请直接输出完整的回忆文章，不要包含任何解释或格式说明。"""

            # --- (调用 DeepSeek API 和流式处理的逻辑保持不变) ---
            try:
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=1.3,
                    max_tokens=1500,
                    stream=True
                )
                generated_content = ""
                chunk_count = 0
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        content_piece = chunk.choices[0].delta.content
                        generated_content += content_piece
                        chunk_count += 1
                        if chunk_count % 3 == 0 or len(generated_content) % 50 == 0:
                            # 注意：这里发送的是 content_piece (增量) 和 full_content (累积)
                            # 前端需要累积 full_content 或直接使用 content_piece 追加
                            # 为了简化前端逻辑，可以只发送 content_piece
                            progress_data = {
                                # 'content': content_piece, # 只发送增量部分
                                'content': content_piece, # 发送增量
                                # 'full_content': generated_content, # 也可以发送累积的，让前端选择
                                'progress': min(90, len(generated_content) / 10),
                                'completed': False
                            }
                            # 确保使用 ensure_ascii=False 并正确格式化 SSE
                            yield f"data: {json.dumps(progress_data, ensure_ascii=False)}\n\n"

                # API调用完成，最终处理
                if generated_content:
                    # --- (更新 session 中 fragment 的逻辑保持不变，但可以添加 user_description) ---
                    with session_lock:
                        if session_id in sessions:
                            session = sessions[session_id]
                            for i, f in enumerate(session['fragments']):
                                if f['id'] == fragment_id:
                                    # 更新内容、状态，并存储用户描述
                                    session['fragments'][i] = {
                                        **f,
                                        'content': generated_content.strip(),
                                        'status': 'generated',
                                        'user_description': user_description, # 存储用户输入
                                        'updated_at': datetime.now().isoformat()
                                    }
                                    break
                            session['last_active'] = datetime.now()
                    # --- (更新逻辑结束) ---

                    # 发送完成事件
                    complete_data = {
                        'content': generated_content.strip(), # 发送最终完整内容
                        'progress': 100,
                        'completed': True
                    }
                    yield f"event: complete\ndata: {json.dumps(complete_data, ensure_ascii=False)}\n\n"
                else:
                    yield f"event: error\ndata: {json.dumps({'error': 'AI没有生成任何内容'}, ensure_ascii=False)}\n\n"
            except Exception as api_error:
                print(f"DeepSeek API调用失败: {api_error}")
                with session_lock:
                    if session_id in sessions:
                        session = sessions[session_id]
                        for i, f in enumerate(session['fragments']):
                            if f['id'] == fragment_id:
                                session['fragments'][i]['status'] = 'new'
                                break
                yield f"event: error\ndata: {json.dumps({'error': f'生成内容失败: {str(api_error)}'}, ensure_ascii=False)}\n\n"
            # --- (API调用和处理逻辑结束) ---

        except Exception as e:
            print(f"generate_content函数错误: {e}")
            try:
                with session_lock:
                    if session_id in sessions:
                        session = sessions[session_id]
                        for i, f in enumerate(session['fragments']):
                            if f['id'] == fragment_id:
                                session['fragments'][i]['status'] = 'new'
                                break
            except:
                pass
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    # 确保响应头正确设置
    return Response(generate(), mimetype="text/event-stream", headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*', # 根据需要调整 CORS
        'X-Accel-Buffering': 'no', # 禁用缓冲，对SSE很重要
    })

# ... (在 Flask 路由部分添加) ...

@app.route('/update_fragment_content', methods=['POST'])
def update_fragment_content():
    """更新回忆碎片的内容和其他字段"""
    data = request.json
    session_id = data.get('session_id')
    fragment_id = data.get('fragment_id')
    content = data.get('content')
    title = data.get('title')
    timeline_date = data.get('timeline_date')
    # status 通常由后端根据 content 是否存在来判断，也可以允许前端更新

    if not session_id or not fragment_id:
        return jsonify({'error': '缺少必要参数'}), 400

    cleanup_expired_sessions()
    with session_lock:
        if session_id not in sessions:
            return jsonify({'error': '会话不存在'}), 404
        session = sessions[session_id]
        fragment_found = False
        for i, fragment in enumerate(session['fragments']):
            if fragment['id'] == fragment_id:
                fragment_found = True
                # 更新字段
                if content is not None:
                    session['fragments'][i]['content'] = content
                    session['fragments'][i]['status'] = 'edited' if fragment.get('content') else 'generated' # 简单状态逻辑
                if title is not None:
                    # 处理标题重复
                    session['fragments'][i]['title'] = get_fragment_title_with_number(session['fragments'], title) if title != fragment['title'] else title
                if timeline_date is not None:
                    session['fragments'][i]['timeline_date'] = timeline_date
                session['fragments'][i]['updated_at'] = datetime.now().isoformat()
                session['last_active'] = datetime.now()
                break
        if not fragment_found:
            return jsonify({'error': '碎片不存在'}), 404
    return jsonify({'success': True})

# ... (之后的代码保持不变) ...



@app.route('/get_fragments', methods=['POST'])
def get_fragments():
    """获取所有回忆碎片"""
    data = request.json
    session_id = data.get('session_id')

    if not session_id:
        return jsonify({'error': '缺少session_id'}), 400

    cleanup_expired_sessions()

    with session_lock:
        if session_id not in sessions:
            return jsonify({'fragments': []})

        fragments = sessions[session_id]['fragments']

        # 排序逻辑：时间轴 > 创建时间 > 自定义顺序
        def sort_key(fragment):
            timeline_date = fragment.get('timeline_date')
            created_at = fragment.get('created_at', '1970-01-01T00:00:00')
            custom_order = fragment.get('custom_order', 999)

            if timeline_date:
                return (0, timeline_date, created_at)
            else:
                return (1, created_at, custom_order)

        sorted_fragments = sorted(fragments, key=sort_key)

        return jsonify({'fragments': sorted_fragments})


@app.route('/delete_fragment', methods=['POST'])
def delete_fragment():
    """删除回忆碎片"""
    data = request.json
    session_id = data.get('session_id')
    fragment_id = data.get('fragment_id')

    if not session_id or not fragment_id:
        return jsonify({'error': '缺少必要参数'}), 400

    cleanup_expired_sessions()

    with session_lock:
        if session_id not in sessions:
            return jsonify({'error': '会话不存在'}), 404

        session = sessions[session_id]
        session['fragments'] = [f for f in session['fragments'] if f['id'] != fragment_id]
        session['last_active'] = datetime.now()

        return jsonify({'success': True})


@app.route('/update_fragment_order', methods=['POST'])
def update_fragment_order():
    """更新碎片顺序"""
    data = request.json
    session_id = data.get('session_id')
    fragment_orders = data.get('fragment_orders')  # [{id: '', order: 0}, ...]

    if not session_id or not fragment_orders:
        return jsonify({'error': '缺少必要参数'}), 400

    cleanup_expired_sessions()

    with session_lock:
        if session_id not in sessions:
            return jsonify({'error': '会话不存在'}), 404

        session = sessions[session_id]

        # 更新每个碎片的自定义顺序
        order_map = {item['id']: item['order'] for item in fragment_orders}

        for fragment in session['fragments']:
            if fragment['id'] in order_map:
                fragment['custom_order'] = order_map[fragment['id']]

        session['last_active'] = datetime.now()

        return jsonify({'success': True})


@app.route('/new_session', methods=['POST'])
def new_session():
    """创建新会话"""
    session_id = str(uuid4())
    with session_lock:
        sessions[session_id] = {
            'fragments': [],
            'last_active': datetime.now()
        }
    return jsonify({'session_id': session_id})


@app.route('/')
def index():
    """提供前端页面"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>岁月存折</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdnjs.cloudflare.com/ajax/libs/Sortable/1.15.0/Sortable.min.js"></script>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                overflow-x: hidden;
            }

            .header {
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                padding: 20px;
                text-align: center;
                color: white;
                border-bottom: 1px solid rgba(255, 255, 255, 0.2);
            }

            .header h1 {
                font-size: 28px;
                font-weight: 600;
                margin-bottom: 10px;
            }

            .scenario-selector {
                display: flex;
                justify-content: center;
                gap: 15px;
                margin-top: 15px;
                flex-wrap: wrap;
            }

            .scenario-btn {
                background: rgba(255, 255, 255, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.3);
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                cursor: pointer;
                transition: all 0.3s ease;
                font-size: 14px;
            }

            .scenario-btn:hover {
                background: rgba(255, 255, 255, 0.3);
                transform: translateY(-2px);
            }

            .scenario-btn.active {
                background: white;
                color: #667eea;
                font-weight: 600;
            }

            .main-container {
                display: flex;
                height: calc(100vh - 120px);
                gap: 20px;
                padding: 20px;
            }

            .theme-words-section {
                width: 35%;
                background: white;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                padding: 20px;
                overflow-y: auto;
            }

            .section-title {
                font-size: 18px;
                font-weight: 600;
                margin-bottom: 15px;
                color: #333;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            .refresh-btn {
                background: #667eea;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 15px;
                cursor: pointer;
                font-size: 12px;
                transition: all 0.3s ease;
            }

            .refresh-btn:hover {
                background: #5a67d8;
                transform: translateY(-1px);
            }

            .refresh-btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }

            .theme-words-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
                gap: 10px;
                margin-bottom: 20px;
            }

            .theme-word {
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                color: white;
                border: none;
                padding: 12px 8px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                text-align: center;
                transition: all 0.3s ease;
                word-break: break-all;
            }

            .theme-word:hover {
                transform: translateY(-3px);
                box-shadow: 0 5px 15px rgba(240, 147, 251, 0.4);
            }

            .loading {
                display: none;
                text-align: center;
                color: #666;
                padding: 20px;
            }

            .fragments-section {
                flex: 1;
                background: white;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                padding: 20px;
                overflow-y: auto;
            }

            .fragments-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 15px;
                margin-top: 15px;
            }

            .fragment-card {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-radius: 12px;
                padding: 20px;
                cursor: pointer;
                transition: all 0.3s ease;
                position: relative;
                min-height: 120px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                text-align: center;
            }

            .fragment-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
            }

            .fragment-card:hover .delete-btn {
                display: block;
            }

            .fragment-title {
                font-size: 16px;
                font-weight: 600;
                margin-bottom: 5px;
            }

            .fragment-status {
                font-size: 12px;
                opacity: 0.8;
            }

            .delete-btn {
                display: none;
                position: absolute;
                top: 8px;
                left: 8px;
                background: #ff4757;
                color: white;
                border: none;
                width: 24px;
                height: 24px;
                border-radius: 50%;
                cursor: pointer;
                font-size: 12px;
                line-height: 1;
                transition: all 0.3s ease;
            }

            .delete-btn:hover {
                background: #ff3838;
                transform: scale(1.1);
            }

            .empty-state {
                text-align: center;
                color: #666;
                padding: 40px 20px;
            }

            .empty-state-icon {
                font-size: 48px;
                margin-bottom: 15px;
                opacity: 0.5;
            }

            .sortable-ghost {
                opacity: 0.5;
            }

            .sortable-drag {
                transform: rotate(5deg);
            }

            @media (max-width: 768px) {
                .main-container {
                    flex-direction: column;
                    height: auto;
                }

                .theme-words-section {
                    width: 100%;
                    max-height: 300px;
                }

                .theme-words-grid {
                    grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>回忆碎片收集器</h1>
            <p>选择一个场景，开始收集属于你的美好回忆</p>
            <div class="scenario-selector" id="scenarioSelector">
                <!-- 场景选择按钮将通过JavaScript动态生成 -->
            </div>
        </div>

        <div class="main-container">
            <div class="theme-words-section">
                <div class="section-title">
                    推荐主题词
                    <button class="refresh-btn" id="refreshBtn" onclick="refreshThemeWords()">
                        换一批 (<span id="refreshCount">0</span>/∞)
                    </button>
                </div>
                <div class="loading" id="themeWordsLoading">正在生成主题词...</div>
                <div class="theme-words-grid" id="themeWordsGrid">
                    <!-- 主题词将通过JavaScript动态生成 -->
                </div>
            </div>

            <div class="fragments-section">
                <div class="section-title">
                    回忆碎片 (<span id="fragmentCount">0</span>)
                    <span style="font-size: 12px; color: #666; font-weight: normal;">
                        点击碎片开始创作，鼠标悬停可删除，支持拖拽排序
                    </span>
                </div>
                <div class="fragments-grid" id="fragmentsGrid">
                    <div class="empty-state">
                        <div class="empty-state-icon">📝</div>
                        <p>还没有回忆碎片<br>点击左侧主题词开始收集吧！</p>
                    </div>
                </div>
            </div>
        </div>

        <script>
            let sessionId = null;
            let currentScenario = 'campus';
            let refreshCount = 0;
            let scenarios = {};
            let fragments = [];
            let currentThemeWords = []; // 新增：存储当前场景的主题词
            
            // 初始化
            async function init() {
                try {
                    // 创建新会话
                    const sessionResponse = await fetch('/new_session', {
                        method: 'POST'
                    });
                    const sessionData = await sessionResponse.json();
                    sessionId = sessionData.session_id;

                    // 获取场景列表
                    const scenariosResponse = await fetch('/get_scenarios');
                    const scenariosData = await scenariosResponse.json();
                    scenarios = scenariosData.scenarios;

                    // 渲染场景选择器
                    renderScenarioSelector();

                    // 加载主题词
                    await loadThemeWords();

                    // 初始化碎片拖拽排序
                    initializeSortable();

                } catch (error) {
                    console.error('初始化失败:', error);
                }
            }

            function renderScenarioSelector() {
                const container = document.getElementById('scenarioSelector');
                container.innerHTML = '';

                Object.entries(scenarios).forEach(([key, scenario]) => {
                    const button = document.createElement('button');
                    button.className = `scenario-btn ${key === currentScenario ? 'active' : ''}`;
                    button.textContent = scenario.name;
                    button.title = scenario.description;
                    button.onclick = () => selectScenario(key);
                    container.appendChild(button);
                });
            }

            async function selectScenario(scenario) {
                if (scenario === currentScenario) return;

                currentScenario = scenario;
                refreshCount = 0;

                // 更新按钮状态
                document.querySelectorAll('.scenario-btn').forEach(btn => {
                    btn.classList.remove('active');
                });
                event.target.classList.add('active');

                // 重新加载主题词
                await loadThemeWords();
                updateRefreshButton();
            }

                        async function loadThemeWords() {
                const loadingEl = document.getElementById('themeWordsLoading');
                const gridEl = document.getElementById('themeWordsGrid');
                const refreshBtn = document.getElementById('refreshBtn');
                
                // 清空当前主题词列表
                currentThemeWords = [];
                renderThemeWords(currentThemeWords); // 先清空显示

                loadingEl.style.display = 'block';
                gridEl.style.display = 'none';
                refreshBtn.disabled = true;

                try {
                    // 使用 Fetch API 和 ReadableStream 来处理 SSE
                    const response = await fetch('/get_theme_words', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            scenario: currentScenario,
                            refresh_count: refreshCount
                        })
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    if (!response.body) {
                        throw new Error('ReadableStream not supported in this browser.');
                    }

                    const reader = response.body.getReader();
                    const decoder = new TextDecoder("utf-8");
                    let buffer = '';

                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;

                        buffer += decoder.decode(value, { stream: true });
                        // 根据 SSE 格式（空行分隔事件）分割
                        const lines = buffer.split(/(\r\n|\r|\n){2}/g);
                        buffer = lines.pop(); // 保留不完整的最后一部分

                        for (const line of lines) {
                            if (line.startsWith("event: ")) {
                                const eventType = line.substring(7);
                                // 可以根据 eventType (init, progress, word, complete) 做不同处理
                                if (eventType === "complete") {
                                    console.log("Theme words loading complete");
                                }
                            } else if (line.startsWith("data: ")) {
                                const dataStr = line.substring(6);
                                try {
                                    const data = JSON.parse(dataStr);
                                    if (data.word) {
                                        // 收到一个新词
                                        currentThemeWords.push(data.word);
                                        renderThemeWords(currentThemeWords); // 实时更新显示
                                    }
                                    // 也可以处理 progress 事件数据
                                } catch (e) {
                                    console.warn("Error parsing SSE data:", e, dataStr);
                                }
                            }
                            // 忽略不匹配的行
                        }
                    }

                    // 确保最后再渲染一次（虽然上面已经实时渲染了，但作为保障）
                    renderThemeWords(currentThemeWords);

                } catch (error) {
                    console.error('加载主题词失败:', error);
                    // 显示默认主题词或错误信息
                    currentThemeWords = ['初见', '心动', '温暖', '微笑', '陪伴', '成长', '梦想', '感动', '拥抱', '告别'];
                    renderThemeWords(currentThemeWords);
                } finally {
                    loadingEl.style.display = 'none';
                    gridEl.style.display = 'grid';
                    refreshBtn.disabled = false;
                }
            }

            // 这个函数应该已经存在，如果没有，请添加
            function renderThemeWords(words) {
                const container = document.getElementById('themeWordsGrid');
                if (!container) return; // 安全检查
                container.innerHTML = '';
                words.forEach(word => {
                    const button = document.createElement('button');
                    button.className = 'theme-word';
                    button.textContent = word;
                    button.onclick = () => createFragment(word);
                    container.appendChild(button);
                });
            }

            async function refreshThemeWords() {
                refreshCount++;
                await loadThemeWords();
                updateRefreshButton();
            }

            function updateRefreshButton() {
                const refreshCountEl = document.getElementById('refreshCount');
                const refreshBtn = document.getElementById('refreshBtn');

                refreshCountEl.textContent = refreshCount;

                if (refreshCount >= 3) {
                    refreshBtn.innerHTML = `换一批 (${refreshCount}/∞) <small>可重复</small>`;
                } else {
                    refreshBtn.innerHTML = `换一批 (${refreshCount}/∞)`;
                }
            }

            async function createFragment(themeWord) {
                try {
                    const response = await fetch('/create_fragment', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            session_id: sessionId,
                            theme_word: themeWord
                        })
                    });

                    const data = await response.json();
                    if (data.fragment) {
                        await loadFragments();
                    }

                } catch (error) {
                    console.error('创建碎片失败:', error);
                }
            }

            async function loadFragments() {
                try {
                    const response = await fetch('/get_fragments', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            session_id: sessionId
                        })
                    });

                    const data = await response.json();
                    fragments = data.fragments || [];
                    renderFragments();

                } catch (error) {
                    console.error('加载碎片失败:', error);
                }
            }

            function renderFragments() {
                const container = document.getElementById('fragmentsGrid');
                const countEl = document.getElementById('fragmentCount');

                countEl.textContent = fragments.length;

                if (fragments.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">📝</div>
                            <p>还没有回忆碎片<br>点击左侧主题词开始收集吧！</p>
                        </div>
                    `;
                    return;
                }

                container.innerHTML = '';

                fragments.forEach(fragment => {
                    const card = document.createElement('div');
                    card.className = 'fragment-card';
                    card.dataset.fragmentId = fragment.id;

                    const statusText = fragment.status === 'new' ? '待创作' : 
                                     fragment.status === 'generated' ? '已生成' : '已编辑';

                    card.innerHTML = `
                        <button class="delete-btn" onclick="deleteFragment('${fragment.id}')" title="删除碎片">×</button>
                        <div class="fragment-title">${fragment.title}</div>
                        <div class="fragment-status">${statusText}</div>
                        ${fragment.timeline_date ? `<div style="font-size: 11px; opacity: 0.7; margin-top: 5px;">${fragment.timeline_date}</div>` : ''}
                    `;

                    card.onclick = (e) => {
                        if (!e.target.classList.contains('delete-btn')) {
                            openFragment(fragment);
                        }
                    };

                    container.appendChild(card);
                });
            }

            async function deleteFragment(fragmentId) {
                if (!confirm('确定要删除这个回忆碎片吗？')) {
                    return;
                }

                try {
                    const response = await fetch('/delete_fragment', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            session_id: sessionId,
                            fragment_id: fragmentId
                        })
                    });

                    if (response.ok) {
                        await loadFragments();
                    }

                } catch (error) {
                    console.error('删除碎片失败:', error);
                }
            }

            function openFragment(fragment) {
                if (fragment.status === 'new') {
                    // 进入交互页面
                    openInteractionPage(fragment);
                } else {
                    // 进入编辑页面
                    openEditPage(fragment);
                }
            }

            function openInteractionPage(fragment) {
                // 创建交互页面模态框
                const modal = document.createElement('div');
                modal.className = 'modal-overlay';
                // 为模态框添加唯一ID，方便查找内部元素
                modal.id = 'interactionModal';
                modal.innerHTML = `
                    <div class="modal-content interaction-modal">
                        <div class="modal-header">
                            <h2>创作回忆碎片：${fragment.title}</h2>
                            <button class="close-btn" onclick="closeModal()">&times;</button>
                        </div>
                        <div class="modal-body">
                            <div class="interaction-area" id="interactionArea">
                                <!-- 初始AI消息 -->
                                <div class="ai-message">
                                    <div class="message-content">
                                        <p>你好！我是你的回忆助手。</p>
                                        <p>让我们一起创作关于 <strong>"${fragment.title}"</strong> 的回忆吧！</p>
                                        <p>请告诉我：这个回忆发生在什么时候？什么地方？有哪些重要的人物？或者任何你想分享的细节？</p>
                                    </div>
                                </div>
                            </div>
                            <div class="input-area">
                                <textarea id="userInput" placeholder="请描述你的回忆..." rows="3"></textarea>
                                <button id="sendBtn" onclick="sendInteractionMessage('${fragment.id}')">发送</button>
                            </div>
                            <!-- 添加一个隐藏的加载指示器 -->
                            <div id="generatingIndicator" style="display:none; padding: 10px; text-align: center; color: #666;">
                                AI 正在创作中...
                            </div>
                        </div>
                    </div>
                `;
                document.body.appendChild(modal);
                const interactionArea = document.getElementById('interactionArea');
                interactionArea.scrollTop = interactionArea.scrollHeight; // 滚动到底部
                document.getElementById('userInput').focus();
            }


            function openEditPage(fragment) {
                // 创建编辑页面模态框
                const modal = document.createElement('div');
                modal.className = 'modal-overlay';
                modal.innerHTML = `
                    <div class="modal-content edit-modal">
                        <div class="modal-header">
                            <h2>编辑回忆碎片：${fragment.title}</h2>
                            <button class="close-btn" onclick="closeModal()">&times;</button>
                        </div>
                        <div class="modal-body">
                            <div class="edit-form">
                                <div class="form-group">
                                    <label>标题</label>
                                    <input type="text" id="editTitle" value="${fragment.title}">
                                </div>
                                <div class="form-group">
                                    <label>时间</label>
                                    <input type="date" id="editDate" value="${fragment.timeline_date || ''}">
                                </div>
                                <div class="form-group">
                                    <label>回忆内容</label>
                                    <textarea id="editContent" rows="15" placeholder="回忆内容...">${fragment.content || ''}</textarea>
                                </div>
                                <div class="form-actions">
                                    <button class="save-btn" onclick="saveFragment('${fragment.id}')">保存</button>
                                    <button class="cancel-btn" onclick="closeModal()">取消</button>
                                </div>
                            </div>
                        </div>
                    </div>
                `;

                document.body.appendChild(modal);
                document.getElementById('editTitle').focus();
            }

            // 修改 sendInteractionMessage 函数以使用流式处理
            async function sendInteractionMessage(fragmentId) {
                const input = document.getElementById('userInput');
                const message = input.value.trim();
                if (!message) return;
            
                const interactionArea = document.getElementById('interactionArea');
                const generatingIndicator = document.getElementById('generatingIndicator');
                const sendBtn = document.getElementById('sendBtn');
            
                // 1. 添加用户消息到界面
                const userMessageDiv = document.createElement('div');
                userMessageDiv.className = 'user-message';
                userMessageDiv.innerHTML = `<div class="message-content">${escapeHtml(message)}</div>`; // 防止XSS
                interactionArea.appendChild(userMessageDiv);
            
                // 2. 清空输入框并禁用输入
                const userDescription = input.value; // 保存用户输入用于发送给后端
                input.value = '';
                input.disabled = true;
                sendBtn.disabled = true;
                generatingIndicator.style.display = 'block'; // 显示生成指示器
            
                // 3. 创建一个容器来显示AI的实时响应
                const aiMessageDiv = document.createElement('div');
                aiMessageDiv.className = 'ai-message';
                const aiContentDiv = document.createElement('div');
                aiContentDiv.className = 'message-content';
                aiContentDiv.innerHTML = '<div id="liveAiOutput" style="white-space: pre-wrap;"></div><div id="aiFinalContent" style="display:none;"></div>';
                aiMessageDiv.appendChild(aiContentDiv);
                interactionArea.appendChild(aiMessageDiv);
            
                // 4. 滚动到最新消息
                interactionArea.scrollTop = interactionArea.scrollHeight;
            
                let fullAiResponse = ""; // 用于累积AI的完整响应
            
                try {
                    // 5. 调用后端流式生成API
                    const response = await fetch('/generate_content', {
                         method: 'POST',
                         headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({
                             session_id: sessionId,
                             fragment_id: fragmentId, // 传递碎片ID
                             user_description: userDescription // 传递用户输入
                         })
                    });
            
                    if (!response.ok) {
                         throw new Error(`HTTP error! status: ${response.status}`);
                    }
            
                    if (!response.body) {
                        throw new Error('ReadableStream not supported in this browser.');
                    }
            
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder("utf-8");
                    let buffer = '';
            
                    // 6. 处理流式数据
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
            
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split(/(\r\n|\r|\n){2}/g);
                        buffer = lines.pop(); // 保留不完整的行
            
                        for (const line of lines) {
                            if (line.startsWith("data: ")) {
                                const dataStr = line.substring(6);
                                try {
                                    const data = JSON.parse(dataStr);
                                    if (data.content) {
                                        fullAiResponse += data.content;
                                        // 实时更新AI输出
                                        document.getElementById('liveAiOutput').textContent = fullAiResponse;
                                        interactionArea.scrollTop = interactionArea.scrollHeight; // 滚动
                                    }
                                    // 可以处理其他字段，如进度 data.progress
                                } catch (e) {
                                    console.warn("Error parsing SSE data:", e, dataStr);
                                }
                            } else if (line.startsWith("event: ")) {
                                const eventType = line.substring(7);
                                if (eventType === "complete") {
                                     console.log("Stream complete");
                                     // 可以在这里处理完成事件的额外逻辑（如果需要）
                                } else if (eventType === "error") {
                                     console.error("Stream error received from server");
                                     // 尝试解析错误信息
                                     const dataLines = lines.slice(lines.indexOf(line) + 1);
                                     for(const dataLine of dataLines) {
                                         if (dataLine.startsWith("data: ")) {
                                             try {
                                                 const errorData = JSON.parse(dataLine.substring(6));
                                                 throw new Error(errorData.error || "Unknown stream error");
                                             } catch (parseErr) {
                                                 console.error("Failed to parse error data:", parseErr);
                                                 throw new Error("An error occurred during generation.");
                                             }
                                         }
                                     }
                                }
                                // 可以处理其他事件类型 (start, progress等)
                            }
                        }
                    }
            
                    // 7. 流结束，更新UI状态
                    generatingIndicator.style.display = 'none';
                    input.disabled = false;
                    sendBtn.disabled = false;
            
                    // 8. 将最终内容放入隐藏的div，并显示完成的UI
                    document.getElementById('liveAiOutput').remove(); // 移除实时显示的div
                    const finalContentDiv = document.getElementById('aiFinalContent');
                    finalContentDiv.style.display = 'block';
                    finalContentDiv.textContent = fullAiResponse; // 或 innerHTML 如果内容是HTML格式
            
                    // 9. 添加“保存为回忆”按钮
                    const saveBtn = document.createElement('button');
                    saveBtn.className = 'edit-generated-btn';
                    saveBtn.textContent = '保存为回忆';
                    saveBtn.onclick = () => saveGeneratedContent(fragmentId, userDescription, fullAiResponse);
                    aiContentDiv.appendChild(saveBtn);
            
                    interactionArea.scrollTop = interactionArea.scrollHeight;
            
                } catch (error) {
                    console.error('Error during streaming:', error);
                    generatingIndicator.style.display = 'none';
                    input.disabled = false;
                    sendBtn.disabled = false;
            
                    // 显示错误信息给用户
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'ai-message';
                    errorDiv.innerHTML = `<div class="message-content" style="background-color: #f8d7da; color: #721c24; border-color: #f5c6cb;">抱歉，生成回忆时出错: ${error.message}</div>`;
                    interactionArea.appendChild(errorDiv);
                    interactionArea.scrollTop = interactionArea.scrollHeight;
                }
            }

            function finishInteraction() {
                // 标记碎片为已生成状态并关闭交互页面
                closeModal();
                // 重新加载碎片列表
                loadFragments();
            }

            async function saveFragment(fragmentId) {
                const title = document.getElementById('editTitle').value.trim();
                const date = document.getElementById('editDate').value;
                const content = document.getElementById('editContent').value.trim();

                if (!title) {
                    alert('请填写标题');
                    return;
                }

                try {
                    // 这里调用后端API保存碎片
                    // const response = await fetch('/save_fragment', {...});

                    // 模拟保存
                    console.log('保存碎片:', { fragmentId, title, date, content });

                    closeModal();
                    await loadFragments();

                } catch (error) {
                    console.error('保存失败:', error);
                    alert('保存失败，请重试');
                }
            }

            function closeModal() {
                const modal = document.querySelector('.modal-overlay');
                if (modal) {
                    modal.remove();
                }
            }
            
            // 新增：保存生成内容的函数
            async function saveGeneratedContent(fragmentId, userDescription, aiContent) {
                 if (!sessionId || !fragmentId) {
                     alert('会话或碎片信息丢失，请刷新页面重试。');
                     return;
                 }
            
                 try {
                     // 调用后端 get_fragments 获取当前碎片信息（包括标题等）
                     const fragmentsResponse = await fetch('/get_fragments', {
                         method: 'POST',
                         headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({ session_id: sessionId })
                     });
                     const fragmentsData = await fragmentsResponse.json();
                     const fragment = fragmentsData.fragments.find(f => f.id === fragmentId);
            
                     if (!fragment) {
                         throw new Error('未找到对应的回忆碎片');
                     }
            
                     // 构造包含对话历史的内容
                     // 格式可以根据需要调整，例如 Markdown 或纯文本
                     const formattedContent = `## 关于 "${fragment.title}" 的回忆\n\n` +
                                              `**用户描述:**\n${userDescription}\n\n` +
                                              `**AI创作:**\n${aiContent}`;
            
                     // 调用一个模拟的或待实现的后端保存接口
                     // 注意：当前后端没有直接的“更新碎片内容”接口，/create_fragment 是创建新碎片
                     // 我们可以复用 /get_fragments 和 /create_fragment 的逻辑，或者建议后端增加一个更新接口
                     // 这里我们模拟直接更新前端显示，并提示用户（因为后端逻辑需要调整才能持久化）
                     // 为了演示，我们直接打开编辑页面，将生成的内容填入
                     closeModal(); // 关闭交互模态框
                     // 模拟创建一个带有生成内容的“fragment”对象用于编辑
                     const generatedFragment = {
                         ...fragment,
                         content: formattedContent, // 使用格式化后的内容
                         status: 'generated',
                         user_description: userDescription // 可选：存储用户原始输入
                     };
                     openEditPage(generatedFragment); // 打开编辑页面，用户可以进一步修改和保存
            
                     // 如果后端有更新接口，可以这样调用：
                     /*
                     const updateResponse = await fetch('/update_fragment_content', {
                         method: 'POST',
                         headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({
                             session_id: sessionId,
                             fragment_id: fragmentId,
                             content: formattedContent, // 传递完整内容
                             status: 'generated'
                             // 可以添加其他字段如 timeline_date
                         })
                     });
            
                     if (updateResponse.ok) {
                         closeModal();
                         await loadFragments(); // 重新加载列表
                         alert('回忆已保存！');
                     } else {
                         const errorData = await updateResponse.json();
                         throw new Error(errorData.error || '保存失败');
                     }
                     */
            
                 } catch (error) {
                     console.error('保存内容失败:', error);
                     alert('保存回忆时出错: ' + error.message);
                 }
            }
            
            
            // 新增：简单的HTML转义函数，防止XSS
            function escapeHtml(unsafe) {
                return unsafe
                     .replace(/&/g, "&amp;")
                     .replace(/</g, "<")
                     .replace(/>/g, ">")
                     .replace(/"/g, "&quot;")
                     .replace(/'/g, "&#039;");
            }


            function initializeSortable() {
                const fragmentsGrid = document.getElementById('fragmentsGrid');

                new Sortable(fragmentsGrid, {
                    animation: 150,
                    ghostClass: 'sortable-ghost',
                    dragClass: 'sortable-drag',
                    filter: '.empty-state, .delete-btn',
                    onEnd: async function(evt) {
                        // 更新碎片顺序
                        const fragmentCards = Array.from(fragmentsGrid.children);
                        const fragmentOrders = fragmentCards.map((card, index) => ({
                            id: card.dataset.fragmentId,
                            order: index
                        })).filter(item => item.id); // 过滤掉空状态元素

                        if (fragmentOrders.length > 0) {
                            try {
                                await fetch('/update_fragment_order', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                    },
                                    body: JSON.stringify({
                                        session_id: sessionId,
                                        fragment_orders: fragmentOrders
                                    })
                                });
                            } catch (error) {
                                console.error('更新顺序失败:', error);
                            }
                        }
                    }
                });
            }

            // 键盘事件处理
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') {
                    closeModal();
                } else if (e.key === 'Enter' && e.ctrlKey) {
                    const userInput = document.getElementById('userInput');
                    if (userInput && document.activeElement === userInput) {
                        sendInteractionMessage();
                    }
                }
            });

            // 页面加载完成后初始化
            window.onload = init;
        </script>

        <style>
            /* 模态框样式 */
            .modal-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                backdrop-filter: blur(5px);
                display: flex;
                justify-content: center;
                align-items: center;
                z-index: 1000;
                animation: fadeIn 0.3s ease-in;
            }

            .modal-content {
                background: white;
                border-radius: 15px;
                max-width: 800px;
                width: 90%;
                max-height: 90vh;
                overflow: hidden;
                box-shadow: 0 20px 40px rgba(0,0,0,0.2);
                animation: slideIn 0.3s ease-out;
            }

            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }

            @keyframes slideIn {
                from { transform: translateY(-30px) scale(0.95); }
                to { transform: translateY(0) scale(1); }
            }

            .modal-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            .modal-header h2 {
                margin: 0;
                font-size: 20px;
            }

            .close-btn {
                background: none;
                border: none;
                color: white;
                font-size: 24px;
                cursor: pointer;
                padding: 0;
                width: 30px;
                height: 30px;
                display: flex;
                justify-content: center;
                align-items: center;
                border-radius: 50%;
                transition: background 0.3s ease;
            }

            .close-btn:hover {
                background: rgba(255, 255, 255, 0.2);
            }

            .modal-body {
                padding: 0;
                height: calc(90vh - 80px);
                overflow-y: auto;
            }

            /* 交互页面样式 */
            .interaction-modal .modal-body {
                display: flex;
                flex-direction: column;
            }

            .interaction-area {
                flex: 1;
                padding: 20px;
                overflow-y: auto;
                background: #f8f9fa;
            }

            .ai-message, .user-message {
                margin-bottom: 20px;
                display: flex;
            }

            .ai-message {
                justify-content: flex-start;
            }

            .user-message {
                justify-content: flex-end;
            }

            .ai-message .message-content {
                background: white;
                border: 1px solid #e9ecef;
                max-width: 80%;
            }

            .user-message .message-content {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                max-width: 80%;
            }

            .message-content {
                padding: 15px 20px;
                border-radius: 20px;
                line-height: 1.5;
            }

            .thinking .message-content {
                background: #e9ecef;
                color: #666;
                font-style: italic;
            }

            .generated-content {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                margin: 10px 0;
                border-left: 4px solid #667eea;
            }

            .generated-content h4 {
                margin: 0 0 10px 0;
                color: #667eea;
            }

            .edit-generated-btn {
                background: #667eea;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 20px;
                cursor: pointer;
                font-size: 14px;
                margin-top: 10px;
            }

            .input-area {
                padding: 20px;
                background: white;
                border-top: 1px solid #e9ecef;
                display: flex;
                gap: 15px;
                align-items: flex-end;
            }

            .input-area textarea {
                flex: 1;
                border: 2px solid #e9ecef;
                border-radius: 10px;
                padding: 12px 15px;
                font-size: 14px;
                font-family: inherit;
                resize: vertical;
                min-height: 60px;
                outline: none;
                transition: border-color 0.3s ease;
            }

            .input-area textarea:focus {
                border-color: #667eea;
            }

            .input-area button {
                background: #667eea;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 10px;
                cursor: pointer;
                font-weight: 500;
                transition: background 0.3s ease;
            }

            .input-area button:hover:not(:disabled) {
                background: #5a67d8;
            }

            .input-area button:disabled {
                background: #ccc;
                cursor: not-allowed;
            }

            /* 编辑页面样式 */
            .edit-form {
                padding: 30px;
            }

            .form-group {
                margin-bottom: 20px;
            }

            .form-group label {
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                color: #333;
            }

            .form-group input,
            .form-group textarea {
                width: 100%;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                padding: 12px 15px;
                font-size: 14px;
                font-family: inherit;
                outline: none;
                transition: border-color 0.3s ease;
            }

            .form-group input:focus,
            .form-group textarea:focus {
                border-color: #667eea;
            }

            .form-group textarea {
                resize: vertical;
                min-height: 200px;
                line-height: 1.6;
            }

            .form-actions {
                display: flex;
                gap: 15px;
                justify-content: flex-end;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #e9ecef;
            }

            .save-btn, .cancel-btn {
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s ease;
            }

            .save-btn {
                background: #28a745;
                color: white;
            }

            .save-btn:hover {
                background: #218838;
            }

            .cancel-btn {
                background: #6c757d;
                color: white;
            }

            .cancel-btn:hover {
                background: #5a6268;
            }
        </style>
    </body>
    </html>
    '''


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
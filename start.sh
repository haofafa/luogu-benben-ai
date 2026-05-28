# 进入项目目录
cd /www/wwwroot/luogu_ai

# 激活虚拟环境
source venv/bin/activate

# 安装所有必要的依赖包
pip install beautifulsoup4 lxml requests flask openai schedule

# 或者安装完整包
pip install beautifulsoup4>=4.12.0 lxml>=4.9.0 requests>=2.31.0 flask>=3.0.0 openai>=1.3.0 schedule>=1.2.0

# 查看已安装的包
pip list

# 测试是否安装成功
python -c "from bs4 import BeautifulSoup; print('BeautifulSoup 安装成功')"
python -c "import requests; print('requests 安装成功')"
python -c "import flask; print('flask 安装成功')"
python -c "import openai; print('openai 安装成功')"

python3 luogu_ai.py &
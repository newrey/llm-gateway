#!/bin/bash

# LLM Gateway Docker镜像发布脚本
# 使用前请确保已安装Docker并登录到Docker Hub

set -e

# 配置变量
IMAGE_NAME="llm-gateway"
DOCKERHUB_USERNAME="newrey"  # 请替换为您的Docker Hub用户名
VERSION="1.0.0"

# 颜色输出函数
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Docker是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装，请先安装Docker"
        exit 1
    fi
    log_info "Docker已安装"
}

# 检查Docker Hub登录状态
check_docker_login() {
    if ! docker info | grep -q "Username"; then
        log_warn "未检测到Docker Hub登录状态"
        log_info "请使用 'docker login' 命令登录Docker Hub"
        exit 1
    fi
    log_info "Docker Hub登录状态正常"
}

# 构建Docker镜像
build_image() {
    log_info "开始构建Docker镜像..."
    docker build -t ${DOCKERHUB_USERNAME}/${IMAGE_NAME}:${VERSION} .
    docker tag ${DOCKERHUB_USERNAME}/${IMAGE_NAME}:${VERSION} ${DOCKERHUB_USERNAME}/${IMAGE_NAME}:latest
    log_info "Docker镜像构建完成"
}

# 测试Docker镜像
test_image() {
    log_info "测试Docker镜像..."
    docker run --rm ${DOCKERHUB_USERNAME}/${IMAGE_NAME}:${VERSION} python -c "import sys; print('Python版本:', sys.version); print('镜像测试通过')"
    log_info "Docker镜像测试通过"
}

# 推送Docker镜像到Docker Hub
push_image() {
    log_info "推送镜像到Docker Hub..."
    docker push ${DOCKERHUB_USERNAME}/${IMAGE_NAME}:${VERSION}
    docker push ${DOCKERHUB_USERNAME}/${IMAGE_NAME}:latest
    log_info "镜像推送完成"
}

# 显示使用说明
show_usage() {
    echo "用法: $0 [选项]"
    echo "选项:"
    echo "  build    仅构建镜像"
    echo "  test     构建并测试镜像"
    echo "  push     构建、测试并推送镜像"
    echo "  all      执行完整流程（构建、测试、推送）"
    echo "  help     显示此帮助信息"
}

# 主函数
main() {
    case "$1" in
        "build")
            check_docker
            build_image
            ;;
        "test")
            check_docker
            build_image
            test_image
            ;;
        "push")
            # check_docker
            # check_docker_login
            build_image
            test_image
            push_image
            ;;
        "all")
            check_docker
            check_docker_login
            build_image
            test_image
            push_image
            ;;
        "help"|"-h"|"--help")
            show_usage
            ;;
        *)
            log_error "无效的选项: $1"
            show_usage
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"

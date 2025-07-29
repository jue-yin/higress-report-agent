"""
报告生成主程序 - 使用重构后的报告生成器系统
"""

import os
from dotenv import load_dotenv
from qwen_agent.agents import Assistant
from tools import GenerateMonthlyReport, GenerateChangelog, GenerateIssueReport
from agent_config import AgentConfig
from report_generator import ReportGeneratorFactory
from qwen_agent.gui import WebUI


class ReportAgent:
    """报告生成代理类 - 封装LLM Agent和报告生成器的交互逻辑"""

    def __init__(self):
        self.llm_assistant = self._init_agent_service()

    def _init_agent_service(self):
        """初始化LLM Agent服务"""
        # LLM配置
        llm_cfg = {
            'model': os.getenv('MODEL_NAME'),
            'model_server': os.getenv('MODEL_SERVER'),
            'api_key': os.getenv('DASHSCOPE_API_KEY'),
            'generate_cfg': {
                'extra_body': {
                    'enable_thinking': False
                },
            },
        }

        # MCP工具配置
        tools = [
            {
                'mcpServers': {
                    'github-mcp-serve': {
                        'command': './github-mcp-serve',
                        "args": ["stdio", "--toolsets", "issues", "--toolsets", "pull_requests", "--read-only", "--toolsets", "repos"],
                        "env": {
                            "GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
                        }
                    },
                }
            },
            'generate_monthly_report_mcp',
            'generate_changelog_mcp',
            'generate_issue_report_mcp',
        ]

        system_prompt = f"""
        你扮演一个报告自动生成助手，严禁调用 github 的写工具
        1. 首先你需要根据用户输入的需求，判断用户是生成月报还是changelog还是修改报告，translate 参数默认是 true
        2. 如果是生成完整（并非修改）月报，你需要调用`generate_monthly_report_mcp`工具来生成月报
        3. 如果是生成完整（并非修改）changelog，你需要调用`generate_changelog_mcp`工具来生成changelog
        4. 如果是生成完整（并非修改）issue报告，你需要调用`generate_issue_report_mcp`工具来生成issue报告
        5. 如果是用户让你修改报告，你需要根据用户的需求，更改生成的报告而不要调用生成报告工具.但用户没提及的部分一定不要修改。
        6. 如果你认为调用函数的信息不全，比如用户没给年月份，是否翻译英文，你一定需要主动询问用户，直到获取到足够的信息。

        示例1（这个 pr 明显不是让你生成月报，而是修改报告，不能调用generate_monthly_report_mcp和generate_changelog_mcp，应该自行分析）：
        Fix an incorrect config proper...
        这个 pr 描述的不太对，帮我改一下功能价值，详细一点

        """

        # 验证GitHub token
        github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
        if not github_token:
            raise ValueError(
                "Missing required environment variable GITHUB_PERSONAL_ACCESS_TOKEN")

        owner = os.getenv("GITHUB_REPO_OWNER", "")
        repo = os.getenv("GITHUB_REPO_NAME", "")
        system_prompt += "\n6. 你可以参考以下GitHub仓库信息来生成报告：\n" \
                         f"   - 仓库所有者: {owner}\n" \
                         f"   - 仓库名称: {repo}\n" \

        # 创建Agent
        bot = Assistant(
            llm=llm_cfg,
            function_list=tools,
            name='github-report-agent',
            description="我是github报告生成助手，可以生成月报、changelog和issue报告！",
            system_message=system_prompt,
        )

        return bot

    def generate_monthly_report(self, month: int = None, year: int = None, important_pr_list: list = None, owner: str = None, repo: str = None, translate: bool = True) -> str:
        """
        生成月报

        Args:
            month: 月份，默认当前月
            year: 年份，默认当前年
            important_pr_list: 重要PR编号列表
            owner: 仓库所有者
            repo: 仓库名称
            translate: 是否生成英文翻译

        Returns:
            月报内容字符串
        """
        print("🚀 开始生成月报...")

        try:
            # 使用工厂模式创建月报生成器
            generator = ReportGeneratorFactory.create_generator("monthly")
            owner = owner or os.getenv('GITHUB_REPO_OWNER', 'alibaba')
            repo = repo or os.getenv("GITHUB_REPO_NAME", "higress")

            # 准备参数
            kwargs = {
                'month': month,
                'year': year,
                'owner': owner,
                'repo': repo,
                'translate': translate
            }

            # 如果有重要PR列表，添加到参数中
            if important_pr_list:
                kwargs['important_pr_list'] = important_pr_list

            # 生成月报
            report = generator.create_report(**kwargs)

            print("✅ 月报生成完成!")
            return report

        except Exception as e:
            print(f"❌ 月报生成失败: {str(e)}")
            return f"月报生成失败: {str(e)}"

    def generate_changelog(self, pr_num_list: list, important_pr_list: list = None, owner: str = None, repo: str = None, translate: bool = True) -> str:
        """
        生成changelog

        Args:
            pr_num_list: PR编号列表
            important_pr_list: 重要PR编号列表
            owner: 仓库所有者
            repo: 仓库名称
            translate: 是否生成英文翻译

        Returns:
            changelog内容字符串
        """
        print("🚀 开始生成changelog...")

        try:
            # 使用工厂模式创建changelog生成器
            generator = ReportGeneratorFactory.create_generator("changelog")

            # 准备参数
            kwargs = {
                'pr_num_list': pr_num_list,
                'owner': owner,
                'repo': repo,
                'translate': translate
            }

            # 如果有重要PR列表，添加到参数中
            if important_pr_list:
                kwargs['important_pr_list'] = important_pr_list

            # 生成changelog
            report = generator.create_report(**kwargs)

            print("✅ Changelog生成完成!")
            return report

        except Exception as e:
            print(f"❌ Changelog生成失败: {str(e)}")
            return f"Changelog生成失败: {str(e)}"

    def generate_issue_report(self, month: int = None, year: int = None, state: str = "open", important_issue_list: list = None, owner: str = None, repo: str = None, translate: bool = True) -> str:
        """
        生成issue报告
        """
        print("🚀 开始生成issue报告...")
        
        try:
            # 使用工厂模式创建issue报告生成器
            generator = ReportGeneratorFactory.create_generator("issue")

            # 准备参数
            kwargs = {
                'month': month,
                'year': year,
                'owner': owner,
                'repo': repo,
                'state': state,
                'translate': translate
            }

            # 如果有重要Issue列表，添加到参数中
            if important_issue_list:
                kwargs['important_issue_list'] = important_issue_list

            # 生成月报
            report = generator.create_report(**kwargs)

            print("✅ issue报告生成完成!")
            return report

        except Exception as e:
            print(f"❌ issue报告生成失败: {str(e)}")
            return f"issue报告生成失败: {str(e)}"
            

    def terminal_interactive_mode(self):
        """交互模式 - 让用户选择生成什么类型的报告"""
        print("🎉 欢迎使用github报告生成器!")

        # 显示当前仓库配置
        default_owner = os.getenv('GITHUB_REPO_OWNER')
        default_repo = os.getenv('GITHUB_REPO_NAME')

        if not default_owner or not default_repo:
            print("❗️ 未设置GITHUB_REPO_OWNER或GITHUB_REPO_NAME环境变量")
            raise ValueError(
                "请设置GITHUB_REPO_OWNER和GITHUB_REPO_NAME环境变量，以便正确生成报告")

        print(f"📂 当前仓库配置: {default_owner}/{default_repo}")
        print("   (可通过环境变量 GITHUB_REPO_OWNER 和 GITHUB_REPO_NAME 修改)")

        print("\n支持的报告类型:")
        print("1. 月报 (monthly)")
        print("2. Changelog (changelog)")
        print("3. 退出 (exit)")

        while True:
            try:
                choice = int(input("\n请选择要生成的报告类型 (1/2/3): ").strip())

                if choice == AgentConfig.REPORT_MONTHLY:
                    # 生成月报
                    month_input = input("请输入月份 (回车使用当前月): ").strip()
                    year_input = input("请输入年份 (回车使用当前年): ").strip()

                    # 询问重要PR
                    print("\n💡 重要PR将获得详细分析，包含使用背景、功能详述、使用方式、功能价值等完整信息")
                    important_input = input(
                        "请输入重要PR编号列表 (用逗号分隔，如: 1234,1235，留空则无重要PR): ").strip()
                    important_pr_list = []
                    if important_input:
                        try:
                            important_pr_list = [
                                int(x.strip()) for x in important_input.split(",")]
                            print(f"✅ 已设置重要PR: {important_pr_list}")
                        except ValueError:
                            print("❌ 重要PR编号格式不正确，将忽略重要PR设置")
                            important_pr_list = []

                    translate_input = input(
                        "是否生成英文翻译? (y/n, 默认y): ").strip().lower()

                    month = int(month_input) if month_input else None
                    year = int(year_input) if year_input else None
                    translate = translate_input != 'n'

                    report = self.generate_monthly_report(
                        month=month,
                        year=year,
                        important_pr_list=important_pr_list,
                        translate=translate
                    )
                    print("\n" + "="*50)
                    print("📋 月报生成完成:")
                    print("="*50)
                    print("✅ 中文报告已保存到: report.md")
                    if translate:
                        print("✅ 英文报告已保存到: report.EN.md")
                    if important_pr_list:
                        print(f"⭐ 重要PR {important_pr_list} 已进行详细分析")
                    print("="*50)

                elif choice == AgentConfig.REPORT_CHANGELOG:
                    # 生成changelog
                    pr_nums_input = input(
                        "请输入PR编号列表 (用逗号分隔，如: 1234,1235,1236): ").strip()

                    if not pr_nums_input:
                        print("❌ 请输入有效的PR编号列表")
                        continue

                    try:
                        pr_num_list = [int(x.strip())
                                       for x in pr_nums_input.split(",")]
                    except ValueError:
                        print("❌ PR编号格式不正确，请输入数字")
                        continue

                    # 询问重要PR
                    important_input = input(
                        "请输入重要PR编号列表 (用逗号分隔，留空则无重要PR): ").strip()
                    important_pr_list = []
                    if important_input:
                        try:
                            important_pr_list = [
                                int(x.strip()) for x in important_input.split(",")]
                            # 验证重要PR是否都在PR列表中
                            invalid_prs = [
                                pr for pr in important_pr_list if pr not in pr_num_list]
                            if invalid_prs:
                                print(f"⚠️ 重要PR {invalid_prs} 不在PR列表中，将自动添加")
                        except ValueError:
                            print("❌ 重要PR编号格式不正确，将忽略重要PR设置")
                            important_pr_list = []

                    translate_input = input(
                        "是否生成英文翻译? (y/n, 默认y): ").strip().lower()
                    translate = translate_input != 'n'

                    owner = os.getenv('GITHUB_REPO_OWNER', 'alibaba')
                    repo = os.getenv('GITHUB_REPO_NAME', 'higress')

                    report = self.generate_changelog(
                        pr_num_list=pr_num_list,
                        important_pr_list=important_pr_list,
                        translate=translate,
                        owner=owner,
                        repo=repo
                    )
                    print("\n" + "="*50)
                    print("📋 Changelog生成完成:")
                    print("="*50)
                    print("✅ 中文报告已保存到: report.md")
                    if translate:
                        print("✅ 英文报告已保存到: report.EN.md")
                    print("="*50)

                elif choice == AgentConfig.EXIT:
                    print("👋 感谢使用github报告生成器，再见!")
                    break

                else:
                    print("❌ 无效选择，请输入 1、2 或 3")

            except KeyboardInterrupt:
                print("\n👋 程序已退出")
                break
            except Exception as e:
                print(f"❌ 发生错误: {str(e)}")

    def interactive_mode(self):
        """ web交互模式 - 让用户选择生成什么类型的报告"""
        print("🎉 欢迎使用github报告生成器!")
        bot = self.llm_assistant
        WebUI(bot).run()

    def cmd_line_args_mode(self, config: AgentConfig):
        """命令行参数模式 - 通过命令行参数生成报告"""
        print("🎉 欢迎使用github报告生成器!")

        # 显示当前仓库配置
        owner = os.getenv('GITHUB_REPO_OWNER')
        repo = os.getenv('GITHUB_REPO_NAME')
        if not owner or not repo:
            print("❗️ 未设置GITHUB_REPO_OWNER或GITHUB_REPO_NAME环境变量")
            raise ValueError(
                "请设置GITHUB_REPO_OWNER和GITHUB_REPO_NAME环境变量，以便正确生成报告")
        print(f"📂 当前仓库配置: {owner}/{repo}")
        print("   (可通过环境变量 GITHUB_REPO_OWNER 和 GITHUB_REPO_NAME 修改)")

        try:
            if config.choice == config.REPORT_MONTHLY:
                report = self.generate_monthly_report(
                    owner=owner,
                    repo=repo,
                    month=config.month,
                    year=config.year,
                    important_pr_list=config.important_pr_list,
                    translate=config.translate
                )
                print("\n" + "="*50)
                print("📋 月报生成完成:")
                print("="*50)
                print("✅ 中文报告已保存到: report.md")
                if config.translate:
                    print("✅ 英文报告已保存到: report.EN.md")
                if config.important_pr_list:
                    print(f"⭐ 重要PR {config.important_pr_list} 已进行详细分析")
                print("="*50)

            elif config.choice == config.REPORT_CHANGELOG:
                report = self.generate_changelog(
                    owner=owner,
                    repo=repo,
                    pr_num_list=config.pr_num_list,
                    important_pr_list=config.important_pr_list,
                    translate=config.translate
                )
                print("\n" + "="*50)
                print("📋 Changelog生成完成:")
                print("="*50)
                print("✅ 中文报告已保存到: report.md")
                if config.translate:
                    print("✅ 英文报告已保存到: report.EN.md")
                print("="*50)
            elif config.choice == config.REPORT_ISSUE:
                report = self.generate_issue_report(
                    owner=owner,
                    repo=repo,
                    month=config.month,
                    year=config.year,
                    state=config.state,
                    important_issue_list=config.important_issue_list,
                    translate=config.translate
                )
                print("\n" + "="*50)
                print("📋 Issue报告生成完成:")
                print("="*50)
                print("✅ 中文报告已保存到: report.md")
                if config.translate:
                    print("✅ 英文报告已保存到: report.EN.md")
                print("="*50)
            else:
                print("❌ 无效选择，请输入 1、2 或 3/4")

        except KeyboardInterrupt:
            print("\n👋 程序已退出")
        except Exception as e:
            print(f"❌ 发生错误: {str(e)}")


def main():
    """主函数"""
    # 加载环境变量
    load_dotenv()
    config = AgentConfig.from_args()

    # 创建报告代理
    agent = ReportAgent()

    isAgent = os.getenv("AGENT", "true")

    # 启动代理
    if config.mode == config.MODE_ARGS:
        agent.cmd_line_args_mode(config)
    elif isAgent == "true":
        agent.interactive_mode()
    else:
        agent.terminal_interactive_mode()


if __name__ == '__main__':
    main()

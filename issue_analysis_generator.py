"""
Issue分析报告生成器 - 自动分析GitHub Issue，总结重点需求
"""
import datetime
from typing import List, Dict, Any, Optional
from report_generator import BaseIssueReportGenerator, IssueInfo
from utils.issue_helper import IssueHelper
from utils.pr_helper import GitHubHelper
from dataclasses import dataclass
import os
import json

class IssueAnalysisReportGenerator(BaseIssueReportGenerator):
    """Issue分析报告生成器"""
    def __init__(self):
        super().__init__()
    
    def get_issue_list(self, **kwargs) -> List[IssueInfo]:
        """获取指定时间范围和标签的issue列表"""
        owner = kwargs.get('owner', self.owner)
        repo = kwargs.get('repo', self.repo)
        month = kwargs.get('month')
        year = kwargs.get('year')
        state = kwargs.get('state', 'open')
        per_page = kwargs.get('perPage', 100)
        max_pages = 20
        issue_list = []
        page = 1
        important_issue_list = kwargs.get('important_issue_list', [])
        
        # 默认当前月
        if not month or not year:
            now = datetime.datetime.now(datetime.timezone.utc)
            month = month or now.month
            year = year or now.year
        print(f"获取{year}年{month}月的Issue列表...")
        if important_issue_list:
            print(f"重要Issue列表: {important_issue_list}")
            
        while page <= max_pages:
            print(f"正在获取第{page}页Issue数据...")
            # 获取已合并的PR
            issues_data = self.github_helper.list_issues(
                owner=owner,
                repo=repo,
                state=state,
                page=page,
                perPage=per_page
            )
            
            if not issues_data:
                break
            # 按月份过滤PR
            filtered_issues = self._filter_issues_by_month(issues_data, month, year)
            for issue in filtered_issues:
                if issue.get("draft", False):
                    continue
                issue_number = issue.get('number', 0)
                issue_info = self._create_issue_info(issue)
                issue_list.append(issue_info)

            # 检查是否还需要继续获取
            if  filtered_issues:
                last_issue = filtered_issues[-1]
                last_issue_year, last_issue_month = GitHubHelper.extract_year_month_from_date(
                    last_issue.get("created_at", "")
                )
                # 如果最后一个PR的日期早于目标月份，停止获取
                if (last_issue_year and last_issue_month and 
                    (last_issue_year < year or (last_issue_year == year and last_issue_month < month))):
                    break

            page += 1

        # 检查是否有重要PR不在月份范围内，如果有则单独获取
        if important_issue_list:
            existing_issue_numbers = {issue.number for issue in issue_list}
            missing_important_issue_list = [issue_num for issue_num in important_issue_list if issue_num not in existing_issue_numbers]
            
            if missing_important_issue_list:
                print(f"发现{len(missing_important_issue_list)}个重要Issue不在当月范围内，单独获取: {missing_important_issue_list}")
                for issue_num in missing_important_issue_list:
                    try:
                        issue_data = self.github_helper.get_issue(
                            owner=owner,
                            repo=repo,
                            issue_number=issue_num
                        )
                        
                        if issue_data:
                            issue_info = self._create_issue_info(issue_data)
                            issue_list.append(issue_info)
                            print(f"✅ 已添加重要Issue #{issue_num}")
                    except Exception as e:
                        print(f"❌ 获取重要Issue #{issue_num}失败: {str(e)}")
        
        print(f"成功获取{len(issue_list)}个Issue，准备进行质量评估...")
        
        return issue_list

    def analyze_issues_with_llm(self, issue_list: List[IssueInfo]) -> List[IssueInfo]:
        """用LLM分析每个issue，提炼需求摘要、优先级、类型等，评论内容也可参与分析"""
        analyzed_issues = []
        print(f"开始分析{len(issue_list)}个Issue...")
        for i, issue in enumerate(issue_list):
            try:
                # 整理评论摘要
                print(f"正在分析Issue #{issue.number}: {issue.title} ({i+1}/{len(issue_list)})") 
                analyzed_issue = self._analyze_single_issue(issue)
                if hasattr(analyzed_issue, 'needed_score') and analyzed_issue.needed_score:
                    analyzed_issues.append(analyzed_issue)
                else:
                    # 如果没有评分，给一个默认评分
                    analyzed_issue.needed_score = 50
                    analyzed_issues.append(analyzed_issue)
                print(f"Issue #{issue.number}分析完成，总分：{analyzed_issue.needed_score}")
            except Exception as e:
                print(f"LLM分析Issue #{issue.number}失败: {str(e)}")
                analyzed_issue.highlight = analyzed_issue.highlight or "需求描述待补充"
                analyzed_issue.function_value = analyzed_issue.function_value or "功能描述待补充"
                analyzed_issue.needed_score = 0
                analyzed_issues.append(analyzed_issue)

         # 按评分降序排序
        analyzed_issues.sort(key=lambda x: x.needed_score, reverse=True)

        # 获取配置的优质PR数量
        import os
        important_issue_num = int(os.getenv("Important_Issue_Num", "100"))
        top_issues = analyzed_issues[:important_issue_num]
        
        print(f"分析完成，从{len(analyzed_issues)}个Issue中选出评分最高的{len(top_issues)}个")
        return top_issues

    def _format_comments_for_analysis(self, comments: list) -> str:
        """将评论内容整理为摘要字符串，供LLM分析使用"""
        if not comments:
            return "无评论"
        summary = []
        for c in comments[:20]:  # 最多取前10条
            user = c.get('user', {}).get('login', '匿名')
            body = c.get('body', '')
            summary.append(f"{user}: {body[:100]}")
        return '\n'.join(summary)

    def _get_analysis_prompt(self) -> str:
        return """
你是一个专业的需求分析师，请先对以下GitHub Issue进行结构化分析，然后基于你的分析结果为其优先级打分。

第一步：结构化分析
- 需求摘要：用一句话总结该issue的核心需求（50字以内）
- 需求类型：feature|refactor|bugfix|doc|test|discussion，并说明理由
    - feature: 新功能、功能增强、新特性
    - bugfix: Bug修复、问题解决
    - doc: 文档更新、文档修复
    - refactor: 代码重构、性能优化、代码清理
    - test: 测试相关、CI/CD改进
    - discussion: 问题讨论、设计探讨

第二步：优先级打分（总分100分）
请从以下六个维度为该issue打分（每个维度为整数），并给出每个维度的分数和简要理由。

1. 用户影响（20分）
 - 高（16-20分）：影响所有用户或核心用户群，解决用户强烈呼吁的痛点，或带来重大体验提升。
 - 中（8-15分）：影响部分用户，属于功能增强、可用性优化，或提升某一类用户体验。
 - 低（1-7分）：影响范围有限，仅涉及极少数用户或内部流程，对大部分用户无明显影响。
 参考：该需求影响了多少用户？是否有用户多次反馈？是否为核心功能？

2. 紧急程度（20分）
 - 高（16-20分）：必须尽快解决，否则会导致业务中断、数据丢失、严重影响用户体验或公司声誉。
 - 中（8-15分）：需要在近期解决，否则会影响后续开发或用户体验，但短期内影响有限。
 - 低（1-7分）：可以延后处理，对当前业务影响不大。
 参考：是否有明确时间要求？不解决会造成什么后果？

3. 业务/战略价值（20分）
 - 高（16-20分）：直接支撑公司核心业务、战略目标或关键增长点。
 - 中（8-15分）：有助于业务发展或提升运营效率，但不是最核心的战略事项。
 - 低（1-7分）：对业务影响有限，属于锦上添花或非战略方向。
 参考：该需求是否与公司当前战略高度相关？是否能带来明显业务增长或成本优化？

4. 社区反馈热度（20分）
 - 高（16-20分）：社区/用户评论数多、点赞数高、讨论热烈，或有外部媒体/大V关注。
 - 中（8-15分）：有一定社区关注，评论或点赞数量中等，部分用户参与讨论。
 - 低（1-7分）：几乎无人关注，评论和点赞很少，或仅为内部成员讨论。
 参考：评论/点赞/关注度如何？是否有社区成员主动参与或推动？

5. 技术复杂度（10分，越简单分数越高）
 - 高（1-3分）：涉及底层架构调整、跨模块重构、复杂算法实现，或需大量测试/验证，风险高。
 - 中（4-7分）：有一定技术挑战，需要跨团队协作或较多开发工作量，但可控。
 - 低（8-10分）：实现简单，改动范围小，风险低，开发周期短。
 参考：是否涉及核心架构或高风险改动？需要多少开发/测试资源？

6. 合规/安全（10分）
 - 高（8-10分）：直接解决合规、法律或安全问题，必须完成，否则有法律/安全风险。
 - 中（4-7分）：有助于提升安全性或合规性，但不是强制要求。
 - 低（1-3分）：与合规/安全无关，或影响极小。
 参考：是否有合规/安全红线或外部监管要求？是否能显著提升系统安全性？

第三步：详细分析（100-300字）：
- 详细分析：对需求进行详细分析，包括需求背景、需求价值、需求实现方式、需求风险等。

使用一段专业化的文字对需求进行分析，可以对解决需求的可能方式进行设想。

issue信息：
编号: {issue_number}
标题: {issue_title}
内容: {issue_body}
评论摘要: {comments_summary}

请严格按照以下JSON格式输出，不要添加任何解释、语言标记、代码块符号（如 ```json）：
{{
  "highlight": "需求概述，关键技术实现方式和原理(50字以上，100字以下)",
  "function_value": "功能价值概要，对社区的影响(50字以上，100字以下)",
  "needed_score": int = （0-100） # 需求评价分数,为上述六个维度的分数总和
  "issue_type": "feature|refactor|bugfix|doc|test|discussion", # 需求类型
  "detailed_analysis": "详细分析内容"
}}
"""



    def generate_report(self, analyzed_issues: List[IssueInfo]) -> str:
        """生成结构化需求总结报告"""
        report = "# 本月重点需求分析报告\n\n"
        if not analyzed_issues:
            report += "本月无有效需求Issue。\n"
            return report
        report += "| 需求分数 | 标题 | 类型 | 需求摘要 |\n"
        report += "|---|---|---|---|\n"
        for issue in analyzed_issues:
            report += f"| {issue.needed_score} | [{issue.title}]({issue.html_url}) | {issue.issue_type} | {issue.highlight} |\n"
        report += "\n\n"
        for issue in analyzed_issues:
            report += f"## [{issue.title}]({issue.html_url})\n"
            report += f"- 编号: #{issue.number}\n"
            report += f"- 类型: {issue.issue_type}\n"
            report += f"- 需求摘要: {issue.highlight}\n"
            report += f"- 功能价值: {issue.function_value}\n"
            report += f"- 详细分析: {issue.detailed_analysis}\n"
            report += f"- 需求评分: {issue.needed_score}/100\n"
            
        return report


    def _get_llm_response(self, messages: list) -> str:
        collected_responses = []
        for response in self.llm_assistant.run(messages=messages):
            if isinstance(response, list) and len(response) > 0:
                for msg in response:
                    if msg.get('role') == 'assistant' and msg.get('content'):
                        collected_responses.append(msg.get('content', ""))
        return collected_responses[-1] if collected_responses else ""


    def _filter_issues_by_month(self, issues_data: List[Dict[str, Any]], month: int, year: int) -> List[Dict[str, Any]]:
            """根据年份和月份过滤issue列表"""
            if not month or not year or not isinstance(issues_data, list):
                return issues_data

            filtered_issues = []
            
            for issue in issues_data:
                created_at = issue.get("created_at")
                if not created_at:
                    continue

                issue_year, issue_month = GitHubHelper.extract_year_month_from_date(created_at)
                if issue_year is not None and issue_month is not None and issue_year == year and issue_month == month:
                    filtered_issues.append(issue)

            return filtered_issues
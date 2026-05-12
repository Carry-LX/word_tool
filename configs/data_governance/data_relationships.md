# 数据联表关系说明

## 总体思路

所有分析都先从目标学科出发，再连接榜单学科名称、排名事实表、指标事实表和对标高校范围。不要让报告生成阶段重新猜表。

## 确定目标学科

联表路径：

- 用户输入：学院或一级学科
- 同济大学学院+学科映射关系20260509.xlsx
- 教育部学科与四大国际学科排名映射关系.xlsx
- 得到四大榜单对应学科名称

输出：

- subject_id
- arwu_subject_name
- qs_subject_name
- usnews_subject_name
- the_subject_area

## 四大排名历史趋势

联表路径：

- dim_subject
- 按榜单对应学科名称筛选年度排名明细
- 按 university_name_cn = 同济大学 筛选
- 统一 release_year、ranking_year、rank_raw、rank_midpoint

输出：

- fact_ranking
- 历史趋势图数据
- 趋势描述

## 对标高校整体分析

联表路径：

- dim_subject
- 全国双一流学科明细表 或 第五轮评估结果确定 peer_scope
- peer_scope 学校名单连接 fact_ranking
- 计算内地排名、分档数量、同济相对位置

输出：

- peer ranking table
- 位次分布表
- 对标结论

## 分项指标分析

联表路径：

- fact_ranking_indicator
- fact_indicator_weight
- peer_scope
- 同学科同年度内重算 indicator_relative_rank

输出：

- 分项指标相对排名图
- 优势/短板指标列表

## 论文实力分析

联表路径：

- 优先查找独立论文库
- 若无独立论文库，使用 US News、软科、THE 中的论文/引用/高被引/国际合作代理指标
- 记录每个指标口径和榜单来源

输出：

- 论文代理指标表
- 数据口径说明
- 谨慎结论

## 国内评估分析

联表路径：

- dim_subject
- 第五轮评估结果（不完全）
- 全国高校第四轮&第三轮学科评估结果
- 全国双一流学科明细表

输出：

- 评估结果对比表
- 国内建设标签
- 数据不完全说明

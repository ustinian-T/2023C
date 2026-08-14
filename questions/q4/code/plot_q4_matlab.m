%% Q4 MATLAB 科研制图
% 直接读取 Q4 已验证的 JSON/CSV 结果，不重新建模或生成展示数据。

clear; close all; clc;

%% 数据读取
scriptDir = fileparts(mfilename('fullpath'));
q4Dir = fileparts(scriptDir);
tableDir = fullfile(q4Dir, 'outputs', 'tables');
resultDir = fullfile(q4Dir, 'outputs', 'results');
figureDir = fullfile(q4Dir, 'outputs', 'figures');
if ~exist(figureDir, 'dir'); mkdir(figureDir); end

summary = jsondecode(fileread(fullfile(resultDir, 'q4_summary.json')));
coverage = readtable(fullfile(tableDir, 'q4_coverage_matrix.csv'), ...
    'VariableNamingRule','preserve','TextType','string');
sensitivity = readtable(fullfile(tableDir, 'q4_sensitivity_analysis.csv'), ...
    'VariableNamingRule','preserve','TextType','string');

%% 变量整理与统一风格
natureColors = [
    110 143 178;
    125 164 148;
    234 182 122;
    229 167 154;
    193 110 113;
    171 200 229;
    216 160 193;
    159 141 184;
    208 208 138] / 255;

paperBg = [1 1 1];
panelBg = [1 1 1];
ink = [43 48 54] / 255;
gridColor = [218 224 228] / 255;
fontName = 'Microsoft YaHei';

set(groot, 'defaultAxesFontName', fontName, 'defaultTextFontName', fontName, ...
    'defaultAxesFontSize', 11, 'defaultAxesLineWidth', 0.8, ...
    'defaultAxesXColor', ink, 'defaultAxesYColor', ink);

%% 图1：前三问可核验诊断证据
k = summary.key_evidence;
evidenceLabels = [
    "Q1 参数分布接受率";
    "Q1 明确单品关系占比";
    "Q2 需求 WAPE";
    "Q2 成本 WAPE";
    "Q2 区间覆盖率";
    "Q2 平均缺货概率";
    "Q2 需求满足率";
    "Q3 候选单品覆盖率";
    "Q3 需求满足率";
    "Q3 选品最小 Jaccard"];
evidenceValues = 100 * [
    k.q1_parametric_accepted / k.q1_distribution_objects;
    k.q1_clear_sku_pairs / k.q1_all_sku_pairs;
    k.q2_demand_wape;
    k.q2_cost_wape;
    k.q2_80pct_coverage;
    k.q2_mean_stockout_probability;
    k.q2_demand_satisfaction;
    k.q3_q1_candidate_coverage / k.q3_candidate_sku_count;
    k.q3_mean_demand_satisfaction;
    k.q3_minimum_selection_jaccard];
evidenceColors = [
    repmat(natureColors(2,:),2,1);
    repmat(natureColors(3,:),5,1);
    repmat(natureColors(1,:),3,1)];

fig = figure('Color',paperBg,'Position',[70 80 1680 760]);
t = tiledlayout(fig,1,3,'TileSpacing','compact','Padding','compact');
title(t,'前三问可核验诊断证据（原始指标，不合成为主观总分）', ...
    'FontSize',20,'FontWeight','bold','Color',ink);
panelGroups = {1:2,3:7,8:10};
panelTitles = {'Q1 规律识别','Q2 预测与服务','Q3 单品决策'};
panelColors = {natureColors(2,:),natureColors(3,:),natureColors(1,:)};
for p = 1:3
    ax = nexttile(t); hold(ax,'on'); idx = panelGroups{p};
    values = evidenceValues(idx); labels = erase(evidenceLabels(idx),["Q1 " "Q2 " "Q3 "]);
    y = 1:numel(idx); c = panelColors{p};
    for i = 1:numel(idx)
        plot(ax,[0 100],[y(i) y(i)],'-','Color',[0.92 0.94 0.95],'LineWidth',8);
        plot(ax,[0 values(i)],[y(i) y(i)],'-','Color',0.74*c+0.26*paperBg,'LineWidth',8);
        scatter(ax,values(i),y(i),145,c,'filled','MarkerEdgeColor','white','LineWidth',1.2);
        text(ax,min(values(i)+2.2,98),y(i),sprintf('%.1f%%',values(i)), ...
            'VerticalAlignment','middle','FontWeight','bold','Color',ink,'FontSize',10.5);
    end
    yticks(ax,y); yticklabels(ax,labels); ax.YDir='reverse';
    ylim(ax,[0.45 numel(idx)+0.55]); xlim(ax,[0 104]); xticks(ax,0:25:100);
    xlabel(ax,'比例或误差（%）'); title(ax,panelTitles{p},'FontSize',15,'FontWeight','bold','Color',c);
    styleAxes(ax,panelBg,gridColor); ax.YGrid='off';
end
exportFigure(fig,fullfile(figureDir,'fig_q4_gap_evidence'));

%% 图2：新增数据包与建模能力的直接覆盖关系
packageNames = ["库存与缺货";"批次损耗与品质";"供应商报价与履约"; ...
    "促销陈列与客流";"匿名购物篮";"天气与日历";"竞争价格"];
capabilityNames = ["识别被缺货截断的真实需求";"控制促销曝光后的价格响应"; ...
    "估计批次动态损耗";"刻画报价和供货不确定性"; ...
    "识别可售集合下的替代与份额";"解释客流与外部需求冲击"; ...
    "核算实际利润和服务水平";"补充相对市场价格背景"];
matrixValues = table2array(coverage(:,2:end));

matrixPriorityColors = zeros(height(sensitivity),3);
for i = 1:height(sensitivity)
    if startsWith(sensitivity.priority_tier(i),"一级")
        matrixPriorityColors(i,:) = natureColors(1,:);
    elseif startsWith(sensitivity.priority_tier(i),"二级")
        matrixPriorityColors(i,:) = natureColors(2,:);
    else
        matrixPriorityColors(i,:) = natureColors(3,:);
    end
end

fig = figure('Color',paperBg,'Position',[55 55 1760 900]);
ax = axes(fig); hold(ax,'on');
for row = 1:size(matrixValues,1)
    for col = 1:size(matrixValues,2)
        scatter(ax,col,row,270,[0.92 0.94 0.95],'filled','Marker','s');
        if matrixValues(row,col)==1
            scatter(ax,col,row,520,matrixPriorityColors(row,:),'filled','Marker','s', ...
                'MarkerEdgeColor','white','LineWidth',1.2);
            scatter(ax,col,row,55,'white','filled','Marker','o');
        end
    end
    rate = sensitivity.inclusion_rate(row);
    plot(ax,[8.75 8.75+1.05*rate],[row row],'-','Color', ...
        0.65*matrixPriorityColors(row,:)+0.35*paperBg,'LineWidth',6);
    scatter(ax,8.75+1.05*rate,row,75,matrixPriorityColors(row,:),'filled', ...
        'MarkerEdgeColor','white','LineWidth',1);
    text(ax,9.93,row,sprintf('%d/7',sensitivity.included_scenario_count(row)), ...
        'HorizontalAlignment','left','VerticalAlignment','middle','FontWeight','bold','Color',ink);
end
xticks(ax,1:numel(capabilityNames)); xticklabels(ax,capabilityNames);
yticks(ax,1:numel(packageNames)); yticklabels(ax,packageNames); ax.YDir='reverse';
ax.XTickLabelRotation=29; ax.TickLength=[0 0]; ax.Box='off'; ax.Color=panelBg;
xlim(ax,[0.45 10.35]); ylim(ax,[0.35 7.65]);
xline(ax,8.45,'-','Color',[0.82 0.84 0.85],'LineWidth',1);
text(ax,9.28,0.18,'情景包含率','HorizontalAlignment','center','FontWeight','bold','Color',ink);
title(ax,'新增数据包—建模能力覆盖及结构情景稳定性', ...
    'FontSize',20,'FontWeight','bold','Color',ink);
exportFigure(fig,fullfile(figureDir,'fig_q4_data_gap_matrix'));

%% 图3：采集优先级的结构情景稳健性
priorityColors = zeros(height(sensitivity),3);
for i = 1:height(sensitivity)
    tier = sensitivity.priority_tier(i);
    if startsWith(tier,"一级")
        priorityColors(i,:) = natureColors(1,:);
    elseif startsWith(tier,"二级")
        priorityColors(i,:) = natureColors(2,:);
    else
        priorityColors(i,:) = natureColors(3,:);
    end
end
counts = sensitivity.included_scenario_count;

fig = figure('Color',paperBg,'Position',[90 70 1580 800]);
ax = axes(fig); hold(ax,'on');
laneColors = {natureColors(3,:),natureColors(2,:),natureColors(1,:)};
for lane=1:3
    rectangle(ax,'Position',[0.55 lane-0.36 6.9 0.72],'Curvature',0.08, ...
        'FaceColor',0.14*laneColors{lane}+0.86*paperBg,'EdgeColor','none');
end
laneY = [3.12 2.18 2.00 2.88 1.82 1.10 0.90];
for i=1:height(sensitivity)
    if strcmpi(sensitivity.selected_in_base(i),"True")
        scatter(ax,counts(i),laneY(i),210,priorityColors(i,:),'filled', ...
            'MarkerEdgeColor','white','LineWidth',1.3);
    else
        scatter(ax,counts(i),laneY(i),210,priorityColors(i,:), ...
            'MarkerFaceColor','white','MarkerEdgeColor',priorityColors(i,:),'LineWidth',2.4);
    end
    align='left'; dx=0.13;
    if counts(i)>=7; align='right'; dx=-0.13; end
    text(ax,counts(i)+dx,laneY(i),sensitivity.data_name(i), ...
        'HorizontalAlignment',align,'VerticalAlignment','middle','Color',ink, ...
        'FontSize',10.5,'FontWeight','bold');
end
yticks(ax,1:3); yticklabels(ax,{'三级：扩展情景采用','二级：核心情景必选','一级：所有情景必选'});
ylim(ax,[0.5 3.5]); xlim(ax,[0.5 7.5]); xticks(ax,1:7); xticklabels(ax,compose('%d/7',1:7));
xlabel(ax,'进入结构情景最小组合的次数');
title(ax,'采集优先级的结构情景轨道图','FontSize',20,'FontWeight','bold','Color',ink);
styleAxes(ax,panelBg,gridColor); ax.YGrid='off';
p1=plot(ax,nan,nan,'o','MarkerSize',10,'MarkerFaceColor',ink,'MarkerEdgeColor','white','LineStyle','none');
p2=plot(ax,nan,nan,'o','MarkerSize',10,'MarkerFaceColor','white','MarkerEdgeColor',ink,'LineWidth',1.8,'LineStyle','none');
legend(ax,[p1 p2],{'进入唯一核心五包组合','仅作为扩展数据'}, ...
    'Location','southoutside','Box','off','NumColumns',2);
exportFigure(fig,fullfile(figureDir,'fig_q4_priority_robustness'));

%% 图4：Q4 数据采集决策复合总览图
fig = figure('Color',paperBg,'Position',[30 30 1900 1080]);
annotation(fig,'textbox',[0.18 0.925 0.64 0.055], ...
    'String','Q4 数据缺口识别、采集组合与价值验证闭环', ...
    'HorizontalAlignment','center','VerticalAlignment','middle', ...
    'FontName',fontName,'FontSize',22,'FontWeight','bold','Color',ink, ...
    'EdgeColor','none');

% 左：关键证据
axL=axes(fig,'Position',[0.085 0.38 0.18 0.49]); hold(axL,'on');
keyIdx=[2 1 3 6 8 10]; keyVals=evidenceValues(keyIdx);
keyLabels=["Q1明确关系";"Q1参数接受";"Q2需求WAPE"; ...
    "Q2缺货概率";"Q3候选覆盖";"Q3最小Jaccard"];
keyColors=[natureColors(2,:);natureColors(2,:);natureColors(3,:); ...
    natureColors(3,:);natureColors(1,:);natureColors(1,:)];
for i=1:numel(keyVals)
    plot(axL,[0 100],[i i],'-','Color',[0.92 0.94 0.95],'LineWidth',7);
    plot(axL,[0 keyVals(i)],[i i],'-','Color',0.72*keyColors(i,:)+0.28*paperBg,'LineWidth',7);
    scatter(axL,keyVals(i),i,105,keyColors(i,:),'filled','MarkerEdgeColor','white');
    text(axL,min(keyVals(i)+2,96),i,sprintf('%.1f%%',keyVals(i)), ...
        'VerticalAlignment','middle','FontWeight','bold','Color',ink,'FontSize',9.5);
end
yticks(axL,1:numel(keyVals)); yticklabels(axL,keyLabels); axL.YDir='reverse';
xlim(axL,[0 103]); ylim(axL,[0.5 numel(keyVals)+0.5]); xticks(axL,0:25:100);
title(axL,'① 前三问证据定位','FontSize',15,'FontWeight','bold','Color',natureColors(5,:));
styleAxes(axL,panelBg,gridColor); axL.YGrid='off';
axL.FontSize=9.5;

% 中：能力覆盖矩阵
axM=axes(fig,'Position',[0.325 0.38 0.40 0.49]); hold(axM,'on');
shortCaps=["真实需求" "价格响应" "动态损耗" "供货成本" "替代份额" "外部需求" "决策验证" "市场背景"];
for row=1:size(matrixValues,1)
    for col=1:size(matrixValues,2)
        scatter(axM,col,row,185,[0.93 0.95 0.96],'filled','Marker','s');
        if matrixValues(row,col)==1
            scatter(axM,col,row,350,matrixPriorityColors(row,:),'filled','Marker','s','MarkerEdgeColor','white');
            scatter(axM,col,row,38,'white','filled');
        end
    end
end
xticks(axM,1:8); xticklabels(axM,shortCaps); axM.XTickLabelRotation=28;
yticks(axM,1:7); yticklabels(axM,packageNames); axM.YDir='reverse';
xlim(axM,[0.45 8.55]); ylim(axM,[0.4 7.6]); axM.TickLength=[0 0]; axM.Box='off';
title(axM,'② 数据包—能力覆盖','FontSize',15,'FontWeight','bold','Color',natureColors(1,:));

% 右：最小组合与三级优先级
axR=axes(fig,'Position',[0.775 0.38 0.19 0.49]); axis(axR,[0 1 0 1]); axis(axR,'off'); hold(axR,'on');
title(axR,'③ 最小组合与优先级','FontSize',15,'FontWeight','bold','Color',natureColors(2,:));
rectangle(axR,'Position',[0.05 0.67 0.90 0.22],'Curvature',0.10, ...
    'FaceColor',0.28*natureColors(1,:)+0.72*paperBg,'EdgeColor',natureColors(1,:),'LineWidth',1.4);
text(axR,0.10,0.84,'一级  7/7','FontWeight','bold','Color',natureColors(1,:),'FontSize',12);
text(axR,0.10,0.745,{'库存与缺货','促销陈列与客流'},'Color',ink,'FontSize',10.5,'VerticalAlignment','middle');
rectangle(axR,'Position',[0.05 0.36 0.90 0.25],'Curvature',0.10, ...
    'FaceColor',0.28*natureColors(2,:)+0.72*paperBg,'EdgeColor',natureColors(2,:),'LineWidth',1.4);
text(axR,0.10,0.56,'二级  5–6/7','FontWeight','bold','Color',natureColors(2,:),'FontSize',12);
text(axR,0.10,0.455,{'批次损耗与品质','供应商报价与履约','匿名购物篮'}, ...
    'Color',ink,'FontSize',10.2,'VerticalAlignment','middle');
rectangle(axR,'Position',[0.05 0.09 0.90 0.20],'Curvature',0.10, ...
    'FaceColor',0.30*natureColors(3,:)+0.70*paperBg,'EdgeColor',natureColors(3,:),'LineWidth',1.4);
text(axR,0.10,0.245,'三级  1/7','FontWeight','bold','Color',natureColors(3,:),'FontSize',12);
text(axR,0.10,0.155,{'天气与日历','竞争价格'},'Color',ink,'FontSize',10.5,'VerticalAlignment','middle');
text(axR,0.50,0.015,'唯一核心组合：5 个数据包','HorizontalAlignment','center', ...
    'FontWeight','bold','Color',natureColors(5,:),'FontSize',11.5);

% 模块间箭头
annotation(fig,'arrow',[0.275 0.315],[0.60 0.60],'Color',[0.55 0.58 0.60],'LineWidth',1.5);
annotation(fig,'arrow',[0.735 0.770],[0.60 0.60],'Color',[0.55 0.58 0.60],'LineWidth',1.5);

% 底部：新增数据后的价值验证闭环
annotation(fig,'textbox',[0.05 0.255 0.90 0.045], ...
    'String','④ 新增数据形成样本后：保持模型边界不变，用同窗口增量回测决定是否长期部署', ...
    'HorizontalAlignment','center','VerticalAlignment','middle','FontName',fontName, ...
    'FontSize',14,'FontWeight','bold','Color',natureColors(5,:),'EdgeColor','none');
boxX=[0.055 0.285 0.515 0.745]; boxW=0.185;
boxText={{'试采集新增数据'}, ...
    {'固定 Q1–Q3 训练窗口、','测试日期与优化边界'}, ...
    {'比较 WAPE、区间校准、','利润、满足率与尾部利润'}, ...
    {'Pareto 支配 + 实际净价值','决定长期采集'}};
boxColors=[natureColors(6,:);natureColors(8,:);natureColors(4,:);natureColors(2,:)];
for i=1:4
    annotation(fig,'textbox',[boxX(i) 0.07 boxW 0.105],'String',boxText{i}, ...
        'HorizontalAlignment','center','VerticalAlignment','middle','FontName',fontName, ...
        'FontSize',11,'FontWeight','bold','Color',ink,'BackgroundColor',0.34*boxColors(i,:)+0.66*paperBg, ...
        'EdgeColor',boxColors(i,:),'LineWidth',1.3,'FitBoxToText','off');
    if i<4
        annotation(fig,'arrow',[boxX(i)+boxW+0.008 boxX(i+1)-0.008],[0.122 0.122], ...
            'Color',[0.48 0.51 0.53],'LineWidth',1.5);
    end
end
exportFigure(fig,fullfile(figureDir,'fig_q4_integrated_decision_dashboard'));

disp('Q4 MATLAB figures completed.');

%% 本地函数
function styleAxes(ax,bg,gridColor)
ax.Color = bg; ax.Box = 'off'; ax.Layer = 'top';
ax.GridColor = gridColor; ax.GridAlpha = 0.55;
ax.XGrid = 'on'; ax.YGrid = 'off'; ax.TickDir = 'out';
end

function exportFigure(fig,basePath)
drawnow;
exportgraphics(fig,[basePath '.png'],'Resolution',300,'BackgroundColor',[1 1 1]);
exportgraphics(fig,[basePath '.pdf'],'ContentType','vector','BackgroundColor',[1 1 1]);
close(fig);
end

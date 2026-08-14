%% Q3 MATLAB 科研制图
% 正式图表仅使用 60 个代表场景求解后、在 600 场景回代评价的主结果。
% 不随机生成展示数据，不读取 600 场景全量优化的逐 SKU 方案。

clear; close all; clc;

%% 数据读取
scriptDir = fileparts(mfilename('fullpath'));
q3Dir = fileparts(scriptDir);
tableDir = fullfile(q3Dir, 'outputs', 'tables');
figureDir = fullfile(q3Dir, 'outputs', 'figures');
if ~exist(figureDir, 'dir'); mkdir(figureDir); end

strategy = readtable(fullfile(tableDir, 'q3_daily_strategy.csv'), 'VariableNamingRule','preserve');
category = readtable(fullfile(tableDir, 'q3_category_summary.csv'), 'VariableNamingRule','preserve');
frontier = readtable(fullfile(tableDir, 'q3_k_frontier.csv'), 'VariableNamingRule','preserve');
sensitivity = readtable(fullfile(tableDir, 'q3_sensitivity_analysis.csv'), 'VariableNamingRule','preserve');
comparison = readtable(fullfile(tableDir, 'q3_model_comparison.csv'), 'VariableNamingRule','preserve');

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
gridColor = [214 216 215] / 255;
fontName = 'Microsoft YaHei';
categoryNames = string(category.category_name);
categoryColors = natureColors(1:height(category), :);

set(groot, 'defaultAxesFontName', fontName, 'defaultTextFontName', fontName, ...
    'defaultAxesFontSize', 11, 'defaultAxesLineWidth', 0.8, ...
    'defaultAxesXColor', ink, 'defaultAxesYColor', ink);

%% 图1：品类层面的选品、补货、满足率与利润
fig = figure('Color', paperBg, 'Position', [80 60 1500 900]);
t = tiledlayout(2,2,'TileSpacing','compact','Padding','compact');
title(t, 'Q3品类层面经营策略与结果', 'FontSize', 20, 'FontWeight','bold', 'Color',ink);

ax1 = nexttile; hold(ax1,'on');
selected = category.selected_sku_count;
unselected = category.candidate_sku_count - selected;
b = barh(ax1, categorical(categoryNames), [selected unselected], 'stacked', 'BarWidth',0.68);
b(1).FaceColor = natureColors(1,:); b(2).FaceColor = [0.86 0.87 0.86];
b(1).EdgeColor = 'none'; b(2).EdgeColor = 'none';
xlabel(ax1,'单品数量'); title(ax1,'候选单品的入选结构','FontWeight','bold');
legend(ax1,{'入选','未入选'},'Location','southeast','Box','off');
styleAxes(ax1,panelBg,gridColor);

ax2 = nexttile; hold(ax2,'on');
bh = barh(ax2, categorical(categoryNames), category.order_qty_kg, 0.62, ...
    'FaceColor','flat','EdgeColor','none');
bh.CData = categoryColors;
for i=1:height(category)
    text(ax2, category.order_qty_kg(i)+2, i, sprintf('%.1f kg',category.order_qty_kg(i)), ...
        'VerticalAlignment','middle','FontSize',10,'Color',ink);
end
xlabel(ax2,'补货量（kg）'); title(ax2,'品类补货量配置','FontWeight','bold');
xlim(ax2,[0 max(category.order_qty_kg)*1.22]); styleAxes(ax2,panelBg,gridColor);

ax3 = nexttile; hold(ax3,'on');
for i=1:height(category)
    plot(ax3,[0 category.mean_demand_satisfaction(i)*100],[i i],'-','Color',0.55*categoryColors(i,:)+0.45*panelBg, ...
        'LineWidth',5);
    scatter(ax3,category.mean_demand_satisfaction(i)*100,i,95,categoryColors(i,:),'filled', ...
        'MarkerEdgeColor','w','LineWidth',1.1);
    text(ax3,category.mean_demand_satisfaction(i)*100+1.2,i,sprintf('%.1f%%',category.mean_demand_satisfaction(i)*100), ...
        'VerticalAlignment','middle','FontSize',10,'Color',ink);
end
yticks(ax3,1:height(category)); yticklabels(ax3,categoryNames); ylim(ax3,[0.5 height(category)+0.5]);
xlim(ax3,[0 102]); xlabel(ax3,'完整场景平均需求满足率');
title(ax3,'品类需求覆盖水平','FontWeight','bold'); styleAxes(ax3,panelBg,gridColor);

ax4 = nexttile; hold(ax4,'on');
profit = category.expected_profit_yuan;
for i=1:height(category)
    c = natureColors(2,:); if profit(i)<0; c=natureColors(5,:); end
    plot(ax4,[0 profit(i)],[i i],'-','Color',0.55*c+0.45*panelBg,'LineWidth',5);
    scatter(ax4,profit(i),i,95,c,'filled','MarkerEdgeColor','w','LineWidth',1.1);
    offset = 5 * sign(profit(i)); if offset==0; offset=5; end
    text(ax4,profit(i)+offset,i,sprintf('%.1f元',profit(i)), ...
        'HorizontalAlignment', ternary(profit(i)<0,'right','left'), ...
        'VerticalAlignment','middle','FontSize',10,'Color',ink);
end
xline(ax4,0,'-','Color',[0.35 0.35 0.35],'LineWidth',0.9);
yticks(ax4,1:height(category)); yticklabels(ax4,categoryNames); ylim(ax4,[0.5 height(category)+0.5]);
xlabel(ax4,'期望利润（元）'); title(ax4,'服务优先下的品类利润贡献','FontWeight','bold');
styleAxes(ax4,panelBg,gridColor);
exportFigure(fig, fullfile(figureDir,'fig_q3_category_strategy'));

%% 图2：单品定价—补货—预期销量气泡图
fig = figure('Color', paperBg, 'Position', [100 80 1400 820]);
ax = axes(fig); hold(ax,'on');
strategyCat = string(strategy.category_name);
for i=1:numel(categoryNames)
    mask = strategyCat==categoryNames(i);
    bubbleSize = 45 + 260 * strategy.expected_sales_kg(mask) ./ max(strategy.expected_sales_kg);
    scatter(ax,strategy.order_qty_kg(mask),strategy.price_yuan_per_kg(mask),bubbleSize, ...
        categoryColors(i,:),'filled','MarkerFaceAlpha',0.80,'MarkerEdgeColor','w','LineWidth',1.0, ...
        'DisplayName',categoryNames(i));
end
[~,labelIdx] = maxk(strategy.order_qty_kg, min(7,height(strategy)));
for k=1:numel(labelIdx)
    i=labelIdx(k);
    text(ax,strategy.order_qty_kg(i)+0.7,strategy.price_yuan_per_kg(i),string(strategy.sku_name(i)), ...
        'FontSize',9,'Color',ink,'VerticalAlignment','middle');
end
xlabel(ax,'补货量（kg）'); ylabel(ax,'零售价（元/kg）');
title(ax,'Q3单品定价与补货组合','FontSize',20,'FontWeight','bold','Color',ink);
legend(ax,'Location','eastoutside','Box','off');
styleAxes(ax,panelBg,gridColor);
exportFigure(fig, fullfile(figureDir,'fig_q3_sku_strategy_bubbles'));

%% 图3：经营单品数量 K 的服务—收益前沿
fig = figure('Color', paperBg, 'Position', [100 80 1450 760]);
ax = axes(fig); hold(ax,'on');
yyaxis(ax,'left');
p1 = plot(ax,frontier.assortment_size,frontier.mean_demand_satisfaction*100,'-o', ...
    'Color',natureColors(1,:),'MarkerFaceColor',natureColors(1,:),'LineWidth',2.6,'MarkerSize',7);
ylabel(ax,'需求满足率（%）');
yyaxis(ax,'right');
p2 = plot(ax,frontier.assortment_size,frontier.expected_profit_yuan,'-s', ...
    'Color',natureColors(2,:),'MarkerFaceColor',natureColors(2,:),'LineWidth',2.6,'MarkerSize',7);
p3 = plot(ax,frontier.assortment_size,frontier.lower10pct_profit_yuan,'--^', ...
    'Color',natureColors(5,:),'MarkerFaceColor',natureColors(5,:),'LineWidth',2.2,'MarkerSize',7);
ylabel(ax,'利润（元）');
xlabel(ax,'经营单品数量 K'); xticks(ax,frontier.assortment_size);
title(ax,'经营单品数量的服务—收益前沿','FontSize',20,'FontWeight','bold','Color',ink);
legend(ax,[p1 p2 p3],{'需求满足率','期望利润','最差10%平均利润'}, ...
    'Location','northwest','Box','off','NumColumns',3);
styleAxes(ax,panelBg,gridColor);
exportFigure(fig, fullfile(figureDir,'fig_q3_k_frontier'));

%% 图4：关键参数灵敏度仪表板
labels = sensitivityLabels(string(sensitivity.variant_id));
baseRow = find(string(sensitivity.variant_id)=='baseline',1);
satDelta = 100*(sensitivity.mean_demand_satisfaction-sensitivity.mean_demand_satisfaction(baseRow));
profitDelta = sensitivity.expected_profit_yuan-sensitivity.expected_profit_yuan(baseRow);
jaccard = sensitivity.selection_jaccard_vs_baseline;

fig = figure('Color', paperBg, 'Position', [80 60 1550 900]);
t = tiledlayout(1,3,'TileSpacing','compact','Padding','compact');
title(t,'Q3关键参数灵敏度与选品稳定性','FontSize',20,'FontWeight','bold','Color',ink);
metrics = {satDelta,profitDelta,jaccard};
xlabels = {'满足率变化（百分点）','期望利润变化（元）','选品Jaccard系数'};
for j=1:3
    ax=nexttile; hold(ax,'on'); values=metrics{j};
    for i=1:height(sensitivity)
        c=natureColors(1+mod(i-1,6),:);
        anchor = 0; if j==3; anchor=1; end
        plot(ax,[anchor values(i)],[i i],'-','Color',0.55*c+0.45*panelBg,'LineWidth',4);
        scatter(ax,values(i),i,80,c,'filled','MarkerEdgeColor','w','LineWidth',1);
    end
    if j<3; xline(ax,0,'--','Color',[0.38 0.38 0.38]); else; xline(ax,1,'--','Color',[0.38 0.38 0.38]); end
    yticks(ax,1:height(sensitivity));
    if j==1; yticklabels(ax,labels); else; yticklabels(ax,repmat("",height(sensitivity),1)); end
    ylim(ax,[0.5 height(sensitivity)+0.5]); xlabel(ax,xlabels{j});
    styleAxes(ax,panelBg,gridColor);
end
exportFigure(fig, fullfile(figureDir,'fig_q3_sensitivity'));

%% 图5：主模型与透明基线对比
modelNames = ["近期销量基线","词典序场景MILP"];
fig = figure('Color', paperBg, 'Position', [120 100 1350 620]);
t = tiledlayout(1,3,'TileSpacing','compact','Padding','compact');
title(t,'Q3主模型与透明基线的同场景比较','FontSize',20,'FontWeight','bold','Color',ink);
vals = {comparison.mean_demand_satisfaction*100, comparison.expected_profit_yuan, comparison.lower10pct_profit_yuan};
names = {'需求满足率（%）','期望利润（元）','最差10%平均利润（元）'};
for j=1:3
    ax=nexttile; hold(ax,'on'); v=vals{j};
    plot(ax,[1 2],v,'-','Color',[0.62 0.64 0.64],'LineWidth',3);
    scatter(ax,1,v(1),130,natureColors(3,:),'filled','Marker','s','MarkerEdgeColor','w');
    scatter(ax,2,v(2),145,natureColors(1,:),'filled','Marker','o','MarkerEdgeColor','w');
    for i=1:2
        text(ax,i,v(i),sprintf('  %.1f',v(i)),'FontWeight','bold','Color',ink,'VerticalAlignment','bottom');
    end
    xlim(ax,[0.65 2.35]); xticks(ax,[1 2]); xticklabels(ax,modelNames);
    title(ax,names{j},'FontWeight','bold'); styleAxes(ax,panelBg,gridColor);
end
exportFigure(fig, fullfile(figureDir,'fig_q3_model_comparison'));

%% 图6（补充）：六品类需求满足率与补货资源分配
% 左：同心极坐标圆弧长度表示需求满足率；右：环形扇区表示补货量占比。
% 两图使用完全一致的品类颜色，避免读者重复辨认编码。
fig = figure('Color', paperBg, 'Position', [80 70 1540 760]);
t = tiledlayout(1,2,'TileSpacing','compact','Padding','compact');
title(t,'Q3六品类需求覆盖与补货资源分配','FontSize',20,'FontWeight','bold','Color',ink);

% 左侧：同心极坐标柱状图
axL = nexttile; hold(axL,'on'); axis(axL,'equal'); axis(axL,'off');
sat = category.mean_demand_satisfaction;
nCat = height(category);
ringWidth = 0.58; ringGap = 0.16; innerRadius = 0.72;
for i = 1:nCat
    r0 = innerRadius + (i-1)*(ringWidth+ringGap);
    r1 = r0 + ringWidth;
    drawAnnularSector(axL,r0,r1,0,2*pi,[0.90 0.90 0.89],[0.90 0.90 0.89],1.0);
    drawAnnularSector(axL,r0,r1,0,2*pi*sat(i),categoryColors(i,:),paperBg,1.2);
    rText = (r0+r1)/2;
    text(axL,0,rText,sprintf('%s  %.1f%%',categoryNames(i),100*sat(i)), ...
        'HorizontalAlignment','center','VerticalAlignment','middle', ...
        'FontSize',9.5,'FontWeight','bold','Color',ink,'BackgroundColor','none');
end
maxR = innerRadius+nCat*(ringWidth+ringGap)-ringGap;
plot(axL,[0 0],[0 maxR+0.05],'-','Color',[0.72 0.72 0.70],'LineWidth',0.7);
text(axL,0,0,'满足率','HorizontalAlignment','center','VerticalAlignment','middle', ...
    'FontSize',11,'FontWeight','bold','Color',ink);
xlim(axL,[-maxR-0.35 maxR+0.35]); ylim(axL,[-maxR-0.35 maxR+0.35]);
title(axL,'各品类需求满足率','FontSize',15,'FontWeight','bold','Color',ink);

% 右侧：补货量占比环形图
axR = nexttile; hold(axR,'on'); axis(axR,'equal'); axis(axR,'off');
orderQty = category.order_qty_kg;
shares = orderQty/sum(orderQty);
startAngle = 0;
donutInner = 1.35; donutOuter = 2.55;
for i = 1:nCat
    endAngle = startAngle + 2*pi*shares(i);
    drawAnnularSector(axR,donutInner,donutOuter,startAngle,endAngle,categoryColors(i,:),paperBg,2.0);
    midAngle = (startAngle+endAngle)/2;
    p1 = polarPoint(donutOuter+0.05,midAngle);
    p2 = polarPoint(donutOuter+0.34,midAngle);
    plot(axR,[p1(1) p2(1)],[p1(2) p2(2)],'-','Color',0.72*categoryColors(i,:)+0.28*ink,'LineWidth',1.0);
    align = 'left'; if p2(1)<0; align='right'; end
    text(axR,p2(1)+0.05*signOrOne(p2(1)),p2(2), ...
        sprintf('%s  %.1f%%',categoryNames(i),100*shares(i)), ...
        'HorizontalAlignment',align,'VerticalAlignment','middle','FontSize',9.5,'Color',ink);
    startAngle = endAngle;
end
text(axR,0,0.14,sprintf('总补货量\n%.1f kg',sum(orderQty)), ...
    'HorizontalAlignment','center','VerticalAlignment','middle', ...
    'FontSize',14,'FontWeight','bold','Color',ink);
text(axR,0,-0.42,'Q2总量 ±0.05% 衔接带内', ...
    'HorizontalAlignment','center','FontSize',9.5,'Color',[0.38 0.42 0.44]);
xlim(axR,[-3.85 3.85]); ylim(axR,[-3.25 3.25]);
title(axR,'各品类补货量占比','FontSize',15,'FontWeight','bold','Color',ink);
exportFigure(fig, fullfile(figureDir,'fig_q3_category_radial_allocation'));

disp('Q3 MATLAB figures completed.');

%% 本地函数
function styleAxes(ax,bg,gridColor)
ax.Color=bg; ax.Box='off'; ax.Layer='top'; ax.GridColor=gridColor;
ax.GridAlpha=0.45; ax.XGrid='on'; ax.YGrid='off'; ax.TickDir='out';
end

function exportFigure(fig,basePath)
drawnow;
exportgraphics(fig,[basePath '.png'],'Resolution',300,'BackgroundColor',fig.Color);
exportgraphics(fig,[basePath '.pdf'],'ContentType','vector','BackgroundColor',fig.Color);
close(fig);
end

function out=ternary(condition,a,b)
if condition; out=a; else; out=b; end
end

function labels=sensitivityLabels(ids)
labels=ids;
labels(ids=='baseline')='基准参数';
labels(ids=='risk_weight_0.00')='风险权重 0';
labels(ids=='risk_weight_0.50')='风险权重 0.5';
labels(ids=='elasticity_scale_0.80')='弹性系数 ×0.8';
labels(ids=='elasticity_scale_1.20')='弹性系数 ×1.2';
labels(ids=='historical_share_weight_0.25')='历史份额权重 0.25';
labels(ids=='historical_share_weight_0.75')='历史份额权重 0.75';
labels(ids=='order_cap_factor_0.850')='补货总量 ×0.85';
labels(ids=='order_cap_factor_0.925')='补货总量 ×0.925';
end

function drawAnnularSector(ax,r0,r1,startAngle,endAngle,faceColor,edgeColor,lineWidth)
% 角度从正上方开始，按顺时针方向增加。
n = max(30,ceil(150*(endAngle-startAngle)/(2*pi)));
theta = linspace(startAngle,endAngle,n);
xOuter = r1*sin(theta); yOuter = r1*cos(theta);
xInner = r0*sin(fliplr(theta)); yInner = r0*cos(fliplr(theta));
patch(ax,[xOuter xInner],[yOuter yInner],faceColor, ...
    'EdgeColor',edgeColor,'LineWidth',lineWidth);
end

function point=polarPoint(radius,angle)
point=[radius*sin(angle),radius*cos(angle)];
end

function value=signOrOne(x)
value=sign(x); if value==0; value=1; end
end

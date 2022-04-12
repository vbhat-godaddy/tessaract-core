var_file=vars/deployment_vars.yaml
rm -rf $var_file
touch $var_file
account_id_text="account_id"
account_id_val=`aws sts get-caller-identity --query "Account" --output text`
echo "$account_id_text: $account_id_val" >> $var_file
team_name_val=`aws ssm get-parameter --name /AdminParams/Team/Name --query "Parameter.Value" --output text`
echo "team_name: $team_name_val" >> $var_file
portfolio_id_val=`aws servicecatalog list-portfolios | jq '.PortfolioDetails[] | select(.DisplayName == "BigDataAnalytics") | .Id' | tr -d '"'`
echo "bigdata_portfolio: $portfolio_id_val" >> $var_file
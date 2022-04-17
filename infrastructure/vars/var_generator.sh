var_file=vars/deployment_vars.yaml
base_file=../tesseract_lambda/src/tesseract/wrappers/base_config.py
rm -rf $var_file
rm -rf $base_file
touch $base_file
touch $var_file
account_id_text="account_id"
account_id_val=`aws sts get-caller-identity --query "Account" --output text`
echo "$account_id_text: $account_id_val" >> $var_file
echo "ACC_ID = '$account_id_val'" >> $base_file
team_name_val=`aws ssm get-parameter --name /AdminParams/Team/Name --query "Parameter.Value" --output text`
echo "team_name: $team_name_val" >> $var_file
echo "TEAM_VAL = '$team_name_val'" >> $base_file
portfolio_id_val=`aws servicecatalog list-portfolios | jq '.PortfolioDetails[] | select(.DisplayName == "BigDataAnalytics") | .Id' | tr -d '"'`
echo "bigdata_portfolio: $portfolio_id_val" >> $var_file
echo "region: $1" >> $var_file
echo "ACC_REGION = '$1'" >> $base_file
environment_val=`aws ssm get-parameter --name /AdminParams/Team/Environment --query "Parameter.Value" --output text`
echo "env_val: $environment_val" >> $var_file
echo "ACC_ENV = '$environment_val'" >> $base_file
cat $var_file
echo "*******"
cat $base_file
"""
Copyright 2019 Goldman Sachs.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
"""
import logging
import re
from typing import Iterable

import gs_quant.target.backtests as backtests
from gs_quant.api.gs.backtests import GsBacktestApi
from gs_quant.backtests.core import Backtest, QuantityType, TradeInMethod
from gs_quant.errors import MqValueError
from gs_quant.target.backtests import *
from gs_quant.target.instrument import EqOption

_logger = logging.getLogger(__name__)

BACKTEST_TYPE_NAME = 'VolatilityFlow'
BACKTEST_TYPE_VALUE = 'Volatility Flow'
EQ_MARKET_MODEL = 'SFK'
ISO_FORMAT = r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$"


class StrategySystematic:
    """Equity back testing systematic strategy"""

    def __init__(self,
                 underliers: Union[EqOption, Iterable[EqOption], EqVarianceSwap, Iterable[EqVarianceSwap]],
                 quantity: float = 1,
                 quantity_type: Union[QuantityType, str] = QuantityType.Notional,
                 trade_in_method: Union[TradeInMethod, str] = TradeInMethod.FixedRoll,
                 roll_frequency: str = None,
                 scaling_method: str = None,
                 index_initial_value: float = 0.0,
                 delta_hedge: DeltaHedgeParameters = None,
                 name: str = None,
                 cost_netting: bool = False,
                 currency: Union[Currency, str] = Currency.USD):
        self.__cost_netting = cost_netting
        self.__currency = get_enum_value(Currency, currency)
        self.__name = name
        self.__backtest_type = BACKTEST_TYPE_NAME

        trade_in_method = get_enum_value(TradeInMethod, trade_in_method).value

        self.__trading_parameters = BacktestTradingParameters(
            quantity=quantity,
            quantity_type=get_enum_value(QuantityType, quantity_type).value,
            trade_in_method=trade_in_method,
            roll_frequency=roll_frequency)

        self.__underliers = []

        if isinstance(underliers, (EqOption, EqVarianceSwap)):
            instrument = underliers
            notional_percentage = 100
            self.check_underlier_fields(instrument)
            self.__underliers.append(BacktestStrategyUnderlier(
                instrument=instrument,
                notional_percentage=notional_percentage,
                hedge=BacktestStrategyUnderlierHedge(risk_details=delta_hedge),
                market_model=EQ_MARKET_MODEL))
        else:
            for underlier in underliers:
                if isinstance(underlier, tuple):
                    instrument = underlier[0]
                    notional_percentage = underlier[1]
                else:
                    instrument = underlier
                    notional_percentage = 100

                if not isinstance(instrument, (EqOption, EqVarianceSwap)):
                    raise MqValueError('The format of the backtest asset is inscorrect.')

                self.check_underlier_fields(instrument)
                self.__underliers.append(BacktestStrategyUnderlier(
                    instrument=instrument,
                    notional_percentage=notional_percentage,
                    hedge=BacktestStrategyUnderlierHedge(risk_details=delta_hedge),
                    market_model=EQ_MARKET_MODEL))

        backtest_parameters_class: Base = getattr(backtests, self.__backtest_type + 'BacktestParameters')
        backtest_parameter_args = {
            'trading_parameters': self.__trading_parameters,
            'underliers': self.__underliers,
            'trade_in_method': trade_in_method,
            'scaling_method': scaling_method,
            'index_initial_value': index_initial_value
        }
        self.__backtest_parameters = backtest_parameters_class.from_dict(backtest_parameter_args)

    @staticmethod
    def check_underlier_fields(
            underlier: Union[EqOption, EqVarianceSwap]
    ) -> bool:
        # validation for different fields
        if isinstance(underlier.expiration_date, datetime.date):
            raise MqValueError('Datetime.date format for expiration date field is not supported for backtest service')
        elif re.search(ISO_FORMAT, underlier.expiration_date) is not None:
            if datetime.datetime.strptime(underlier.expiration_date, "%Y-%m-%d"):
                raise MqValueError('Date format for expiration date field is not supported for backtest service')

        return True

    def backtest(
            self,
            start: datetime.date = None,
            end: datetime.date = datetime.date.today() - datetime.timedelta(days=1),
            is_async: bool = False,
            measures: Iterable[FlowVolBacktestMeasure] = (FlowVolBacktestMeasure.ALL_MEASURES,),
            correlation_id: str = None
    ) -> Union[Backtest, BacktestResult]:

        params_dict = self.__backtest_parameters.as_dict()
        params_dict['measures'] = [m.value for m in measures]
        backtest_parameters_class: Base = getattr(backtests, self.__backtest_type + 'BacktestParameters')
        params = backtest_parameters_class.from_dict(params_dict)

        backtest = Backtest(name=self.__name,
                            mq_symbol=self.__name,
                            parameters=params,
                            start_date=start,
                            end_date=end,
                            type=BACKTEST_TYPE_VALUE,
                            asset_class=AssetClass.Equity,
                            currency=self.__currency,
                            cost_netting=self.__cost_netting)

        if is_async:
            # Create back test ...
            response = GsBacktestApi.create_backtest(backtest)

            # ... and schedule it
            GsBacktestApi.schedule_backtest(backtest_id=response.id)
        else:
            # Run on-the-fly back test
            response = GsBacktestApi.run_backtest(backtest, correlation_id)

        return response

# calculate_variable_tax

import frappe
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from hrms.payroll.doctype.salary_slip.salary_slip import set_loan_repayment,calculate_tax_by_tax_slab
from frappe.utils import (
	add_days,
	ceil,
	cint,
	cstr,
	date_diff,
	floor,
	flt,
	formatdate,
	get_first_day,
	get_last_day,
	get_link_to_form,
	getdate,
	money_in_words,
	rounded,
)
from frappe.query_builder.functions import Count, Sum
class CustomSalarySlip(SalarySlip):
    ### make period = 12
    ### Assigned self.remaining_sub_periods = 12
    def calculate_net_pay(self, skip_tax_breakup_computation: bool = False):
      
      def set_gross_pay_and_base_gross_pay():
        self.gross_pay = self.get_component_totals("earnings", depends_on_payment_days=1)
        self.base_gross_pay = flt(
          flt(self.gross_pay) * flt(self.exchange_rate), self.precision("base_gross_pay")
        )

      if self.salary_structure:
        self.calculate_component_amounts("earnings")
      if self.payroll_period:
        self.remaining_sub_periods = 12

      set_gross_pay_and_base_gross_pay()

      if self.salary_structure:
        self.calculate_component_amounts("deductions")

      set_loan_repayment(self)

      self.set_precision_for_component_amounts()
      self.set_net_pay()
      if not skip_tax_breakup_computation:
        self.compute_income_tax_breakup()
    def compute_taxable_earnings_for_year(self):
      # get taxable_earnings, opening_taxable_earning, paid_taxes for previous period
      self.previous_taxable_earnings, exempted_amount = self.get_taxable_earnings_for_prev_period(
        self.payroll_period.start_date, self.start_date, self.tax_slab.allow_tax_exemption
      )

      self.previous_taxable_earnings_before_exemption = self.previous_taxable_earnings + exempted_amount

      self.compute_current_and_future_taxable_earnings()

      # Deduct taxes forcefully for unsubmitted tax exemption proof and unclaimed benefits in the last period
      if self.payroll_period.end_date <= getdate(self.end_date):
        self.deduct_tax_for_unsubmitted_tax_exemption_proof = 1
        self.deduct_tax_for_unclaimed_employee_benefits = 1

      # Get taxable unclaimed benefits
      self.unclaimed_taxable_benefits = 0
      if self.deduct_tax_for_unclaimed_employee_benefits:
        self.unclaimed_taxable_benefits = self.calculate_unclaimed_taxable_benefits()

      # Total exemption amount based on tax exemption declaration
      self.total_exemption_amount = self.get_total_exemption_amount()

      # Employee Other Incomes
      self.previous_axable_earnings = 0
      # frappe.msgprint(f"sec is {self.previous_axable_earnings}")
      self.other_incomes = self.get_income_form_other_sources() or 0.0
      # Total taxable earnings including additional and other incomes


    #   self.total_taxable_earnings = (
		# 	 self.current_structured_taxable_earnings *12
		# 	+ self.current_additional_earnings
		# 	+ self.other_incomes
		# 	+ self.unclaimed_taxable_benefits
		# 	- self.total_exemption_amount
		# )






      self.total_taxable_earnings = (
        self.previous_axable_earnings
        + self.current_structured_taxable_earnings * 12
        + self.future_structured_taxable_earnings
        + self.current_additional_earnings
        + self.other_incomes
        + self.unclaimed_taxable_benefits
        - self.total_exemption_amount
      )



      self.total_taxable_earnings_without_full_tax_addl_components = (
        self.total_taxable_earnings - self.current_additional_earnings_with_full_tax
      )
    def get_component_totals(self, component_type, depends_on_payment_days=0):
      total = 0.0
      for d in self.get(component_type):
        if not d.do_not_include_in_total:
          if depends_on_payment_days:
            amount = self.get_amount_based_on_payment_days(d)[0]
          else:
            amount = flt(d.amount, d.precision("amount"))
          total += amount
      return total    
    def get_amount_based_on_payment_days(self, row):
      amount, additional_amount = row.amount, row.additional_amount
      timesheet_component = self._salary_structure_doc.salary_component

      if (
        self.salary_structure
        and cint(row.depends_on_payment_days)
        and cint(self.total_working_days)
        and not (
          row.additional_salary and row.default_amount
        )  # to identify overwritten additional salary
        and (
          row.salary_component != timesheet_component
          or getdate(self.start_date) < self.joining_date
          or (self.relieving_date and getdate(self.end_date) > self.relieving_date)
        )
      ):
        additional_amount = flt(
          (flt(row.additional_amount) * flt(self.payment_days) / cint(self.total_working_days)),
          row.precision("additional_amount"),
        )
        amount = (
          flt(
            (flt(row.default_amount) * flt(self.payment_days) / cint(self.total_working_days)),
            row.precision("amount"),
          )
          + additional_amount
        )

      elif (
        not self.payment_days
        and row.salary_component != timesheet_component
        and cint(row.depends_on_payment_days)
      ):
        amount, additional_amount = 0, 0
      elif not row.amount:
        amount = flt(row.default_amount) + flt(row.additional_amount)

      # apply rounding
      if frappe.db.get_value(
        "Salary Component", row.salary_component, "round_to_the_nearest_integer", cache=True
      ):
        amount, additional_amount = rounded(amount or 0), rounded(additional_amount or 0)

      return amount, additional_amount

    ###1- assigned self.previous_total_paid_taxes = 0
    def calculate_variable_tax(self, tax_component):
      self.previous_total_paid_taxes = 0
      eval_locals, default_data = self.get_data_for_eval()
      self.total_structured_tax_amount = calculate_tax_by_tax_slab(
        self.total_taxable_earnings_without_full_tax_addl_components,
        self.tax_slab,
        self.whitelisted_globals,
        eval_locals,
      )
      self.current_structured_tax_amount = (
        self.total_structured_tax_amount - self.previous_total_paid_taxes
      ) / self.remaining_sub_periods
      # Total taxable earnings with additional earnings with full tax
      self.full_tax_on_additional_earnings = 0.0
      if self.current_additional_earnings_with_full_tax:
        self.total_tax_amount = calculate_tax_by_tax_slab(
          self.total_taxable_earnings, self.tax_slab, self.whitelisted_globals, eval_locals
        )
        self.full_tax_on_additional_earnings = self.total_tax_amount - self.total_structured_tax_amount

      current_tax_amount = self.current_structured_tax_amount + self.full_tax_on_additional_earnings
      if flt(current_tax_amount) < 0:
        current_tax_amount = 0

      self._component_based_variable_tax[tax_component].update(
        {
          "previous_total_paid_taxes": self.previous_total_paid_taxes,
          "total_structured_tax_amount": self.total_structured_tax_amount,
          "current_structured_tax_amount": self.current_structured_tax_amount,
          "full_tax_on_additional_earnings": self.full_tax_on_additional_earnings,
          "current_tax_amount": current_tax_amount,
        }
      )
      return current_tax_amount